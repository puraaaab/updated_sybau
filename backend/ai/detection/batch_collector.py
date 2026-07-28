import time
import logging
import asyncio
from typing import List, Dict, Any
import numpy as np

stream_manager = None


def _get_stream_manager():
    global stream_manager
    if stream_manager is not None:
        return stream_manager
    try:
        from ...services.stream_manager import stream_manager as manager
    except (ImportError, ValueError):
        from backend.services.stream_manager import stream_manager as manager
    stream_manager = manager
    return stream_manager

from .yolo import detect_and_track_batch

logger = logging.getLogger(__name__)


class DeadlinedBatchCollector:
    def __init__(self, max_batch_size: int = 4, max_wait_ms: float = 40.0, base_skip_interval: int = 3, skip_interval: int = None):
        """
        Manages high-speed frame aggregation from shared memory with an adaptive frame-skipping safety mechanism.

        Args:
            max_batch_size: Maximum number of camera streams grouped into a single CUDA tensor.
            max_wait_ms: Maximum duration (in milliseconds) to wait for new frames before forcing processing.
            base_skip_interval: Baseline frame cadence logic passed downstream to YOLO (default 3).
        """
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms / 1000.0  # Convert to seconds for time selectors
        
        # Adaptive Load Shedding Configuration
        self.base_skip_interval = skip_interval if skip_interval is not None else base_skip_interval
        self.current_skip_interval = self.base_skip_interval
        self.max_skip_interval = 6
        
        # Performance Tracking (Exponential Moving Average)
        self.batch_latency_ema = 0.015  # Initialize assuming a healthy 15ms inference time
        self.ema_alpha = 0.15           # Weight for new measurements
        
        # Thresholds (In Seconds)
        self.LATENCY_UP_THRESHOLD = 0.035   # Spike: Exceeding 35ms triggers load shedding
        self.LATENCY_DOWN_THRESHOLD = 0.020 # Safe: Falling below 20ms restores fidelity

        # Tracks the frame index sequence per camera stream across aggregation loops
        self.stream_frame_counters: Dict[str, int] = {}
        # Tracks the last processed frame timestamp to identify truly fresh frames
        self.last_frame_timestamps: Dict[str, float] = {}

    def _update_adaptive_cadence(self, execution_time: float):
        """
        Maintains an exponential moving average of execution latency and adjusts skip pacing.
        """
        # Update our moving average
        self.batch_latency_ema = (self.ema_alpha * execution_time) + ((1 - self.ema_alpha) * self.batch_latency_ema)
        
        # Thermal / Occlusion Load Shedding Logic
        if self.batch_latency_ema > self.LATENCY_UP_THRESHOLD and self.current_skip_interval < self.max_skip_interval:
            self.current_skip_interval += 1
            logger.warning(
                f"🚨 High GPU load detected! Batch EMA: {self.batch_latency_ema*1000:.1f}ms. "
                f"Shedding load: skip_interval increased to {self.current_skip_interval}."
            )
        elif self.batch_latency_ema < self.LATENCY_DOWN_THRESHOLD and self.current_skip_interval > self.base_skip_interval:
            self.current_skip_interval -= 1
            logger.info(
                f"✅ GPU Performance recovered. Batch EMA: {self.batch_latency_ema*1000:.1f}ms. "
                f"Restoring fidelity: skip_interval lowered to {self.current_skip_interval}."
            )

    def collect_and_process_batch(self, active_stream_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Gathers frames from shared memory, respecting deadlines and dynamically shifting frame cadence.
        """
        start_time = time.perf_counter()

        frames_collected: List[np.ndarray] = []
        streams_in_batch: List[str] = []
        counters_in_batch: List[int] = []

        # Track which streams we still need to wait for in this cycle. Do not
        # truncate here: deployments may have more live cameras than a single
        # CUDA batch. We collect all fresh frames before chunking inference into
        # max_batch_size groups below.
        pending_streams = list(active_stream_ids)

        while pending_streams:
            current_time = time.perf_counter()
            elapsed_time = current_time - start_time

            # Deadline enforcement: if time is up, fire the batch immediately with what we have
            if elapsed_time >= self.max_wait_ms:
                if len(frames_collected) > 0:
                    logger.warning(
                        f"Batch deadline of {self.max_wait_ms*1000:.1f}ms reached. "
                        f"Firing partial batch ({len(frames_collected)}/{len(active_stream_ids)} streams). "
                        f"Skipped lagging streams: {pending_streams}"
                    )
                break

            # Iterate through remaining pending streams to pull from shared memory
            for stream_id in list(pending_streams):
                stream_obj = _get_stream_manager().get_stream(stream_id)
                if stream_obj is None:
                    pending_streams.remove(stream_id)
                    continue

                # Fetch from shared memory via thread mutex
                latest_frame, frame_timestamp = stream_obj.get_latest_frame()

                if latest_frame is None:
                    continue

                # Check if this frame is actually new compared to our last processed cycle
                last_seen_ts = self.last_frame_timestamps.get(stream_id, 0.0)

                if frame_timestamp > last_seen_ts:
                    # Increment internal tracking sequence counter
                    self.stream_frame_counters[stream_id] = self.stream_frame_counters.get(stream_id, 0) + 1
                    self.last_frame_timestamps[stream_id] = frame_timestamp

                    # Add to current batch pipeline arrays
                    frames_collected.append(latest_frame)
                    streams_in_batch.append(stream_id)
                    counters_in_batch.append(self.stream_frame_counters[stream_id])

                    # Remove from pending queue
                    pending_streams.remove(stream_id)

            # Tiny sleep to avoid hot-looping the CPU core while waiting for the RTSP mutex
            if pending_streams:
                time.sleep(0.002)

        if not frames_collected:
            return {stream_id: [] for stream_id in active_stream_ids}

        # Measure explicit execution overhead of the batch inference block
        inference_start = time.perf_counter()

        # Dispatch frames in bounded chunks so all active cameras get a chance
        # to be processed while respecting max_batch_size VRAM limits.
        results = {stream_id: [] for stream_id in active_stream_ids}
        for offset in range(0, len(frames_collected), self.max_batch_size):
            chunk_results = detect_and_track_batch(
                frames=frames_collected[offset:offset + self.max_batch_size],
                stream_ids=streams_in_batch[offset:offset + self.max_batch_size],
                frame_counters=counters_in_batch[offset:offset + self.max_batch_size],
                skip_interval=self.current_skip_interval,
            )
            results.update(chunk_results)

        inference_duration = time.perf_counter() - inference_start

        # Recalculate throttling settings based on this cycle's performance
        self._update_adaptive_cadence(inference_duration)

        return results
