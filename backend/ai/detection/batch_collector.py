import time
import logging
import asyncio
from typing import List, Dict, Any
import numpy as np

try:
    from ...services.stream_manager import stream_manager
except (ImportError, ValueError):
    from backend.services.stream_manager import stream_manager

from .yolo import detect_and_track_batch

logger = logging.getLogger(__name__)


class DeadlinedBatchCollector:
    def __init__(self, max_batch_size: int = 4, max_wait_ms: float = 40.0, skip_interval: int = 3):
        """
        Manages high-speed frame aggregation from shared memory with a strict time deadline.

        Args:
            max_batch_size: Maximum number of camera streams grouped into a single CUDA tensor.
            max_wait_ms: Maximum duration (in milliseconds) to wait for new frames before forcing processing.
            skip_interval: Frame cadence logic passed downstream to YOLO.
        """
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms / 1000.0  # Convert to seconds for time selectors
        self.skip_interval = skip_interval

        # Tracks the frame index sequence per camera stream across aggregation loops
        self.stream_frame_counters: Dict[str, int] = {}
        # Tracks the last processed frame timestamp to identify truly fresh frames
        self.last_frame_timestamps: Dict[str, float] = {}

    def collect_and_process_batch(self, active_stream_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Gathers frames from shared memory, respecting the max_wait_ms deadline.
        Fires an incomplete batch immediately if the timeout expires.
        """
        start_time = time.perf_counter()

        frames_collected: List[np.ndarray] = []
        streams_in_batch: List[str] = []
        counters_in_batch: List[int] = []

        # Track which streams we still need to wait for in this cycle
        pending_streams = list(active_stream_ids[:self.max_batch_size])

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
                stream_obj = stream_manager.get_stream(stream_id)
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

        # 4. Dispatch the synchronized batch array into the CUDA pipeline
        return detect_and_track_batch(
            frames=frames_collected,
            stream_ids=streams_in_batch,
            frame_counters=counters_in_batch,
            skip_interval=self.skip_interval
        )
