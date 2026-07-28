import pytest
import time
import numpy as np
from unittest.mock import MagicMock, patch

from backend.ai.detection.batch_collector import DeadlinedBatchCollector


class MockStream:
    def __init__(self, frame_shape=(1080, 1920, 3)):
        self.frame = np.zeros(frame_shape, dtype=np.uint8)
        self.timestamp = time.perf_counter()

    def get_latest_frame(self):
        # Dynamically increment timestamp slightly on each read to simulate a live camera feed
        self.timestamp += 0.040  # 25 FPS cadenced arrival
        return self.frame, self.timestamp


@pytest.fixture
def mock_stream_manager():
    """Mocks the shared-memory stream manager layer."""
    with patch("backend.ai.detection.batch_collector.stream_manager") as mock_mgr:
        streams = {
            "cam_fast_1": MockStream(),
            "cam_fast_2": MockStream(),
            "cam_fast_3": MockStream(),
            "cam_lagging_4": MockStream()
        }
        mock_mgr.get_stream.side_effect = lambda stream_id: streams.get(stream_id)
        yield mock_mgr, streams


@patch("backend.ai.detection.batch_collector.detect_and_track_batch")
def test_deadline_enforcement_on_lagging_stream(mock_yolo_batch, mock_stream_manager):
    """
    PROVE: If a camera stops producing frames (network jitter/drop), the collector 
    must fire a partial batch exactly at the max_wait_ms deadline.
    """
    mock_mgr, streams = mock_stream_manager
    # Set a strict 40ms wait deadline
    collector = DeadlinedBatchCollector(max_batch_size=4, max_wait_ms=40.0, base_skip_interval=3)
    
    # Simulate a total freeze on the lagging wireless camera
    streams["cam_lagging_4"].get_latest_frame = MagicMock(return_value=(None, 0.0))
    
    start_run = time.perf_counter()
    active_cameras = ["cam_fast_1", "cam_fast_2", "cam_fast_3", "cam_lagging_4"]
    
    # Execute batch harvesting loop
    collector.collect_and_process_batch(active_cameras)
    duration = time.perf_counter() - start_run

    # ASSERT: The processing loop did not hang; it broke out near the 40ms deadline
    assert duration >= 0.040, "Batch fired too fast without trying to wait."
    assert duration < 0.070, "Batch breached the strict deadline limit, causing pipeline drag!"
    
    # ASSERT: YOLO was still called with the 3 healthy streams that were ready
    mock_yolo_batch.assert_called_once()
    called_kwargs = mock_yolo_batch.call_args[1]
    assert len(called_kwargs["frames"]) == 3
    assert "cam_lagging_4" not in called_kwargs["stream_ids"]


def test_adaptive_ema_load_shedding_upshift():
    """
    PROVE: Sustained high inference latency (thermal throttling) causes the 
    skip_interval to upshift to shield the GPU and switch to CPU Kalman tracking.
    """
    collector = DeadlinedBatchCollector(max_batch_size=4, max_wait_ms=40.0, base_skip_interval=3)
    assert collector.current_skip_interval == 3

    # Inject a sustained 80ms processing spike across multiple cycles
    for _ in range(5):
        collector._update_adaptive_cadence(0.080)
        
    # ASSERT: Moving average recognized sustained stress and maxed out load shedding
    assert collector.batch_latency_ema > 0.035
    assert collector.current_skip_interval == collector.max_skip_interval  # Must be 6


def test_adaptive_ema_recovery_downshift():
    """
    PROVE: When temperatures cool and latency drops, the collector automatically 
    downshifts back down to maximize detection fidelity.
    """
    collector = DeadlinedBatchCollector(max_batch_size=4, max_wait_ms=40.0, base_skip_interval=3)
    
    # Force the collector into a throttled state first (Interval 6)
    collector.current_skip_interval = 6
    collector.batch_latency_ema = 0.055

    # Inject cold, fast 10ms execution cycles
    for _ in range(25):
        collector._update_adaptive_cadence(0.010)

    # ASSERT: The system recovered perfectly to its baseline tracking cadence
    assert collector.batch_latency_ema < 0.020
    assert collector.current_skip_interval == collector.base_skip_interval  # Restored to 3


@patch("backend.ai.detection.batch_collector.detect_and_track_batch")
def test_all_active_streams_are_chunked_not_dropped(mock_yolo_batch, mock_stream_manager):
    """Cameras beyond max_batch_size must still be processed in later chunks."""
    mock_mgr, streams = mock_stream_manager
    streams["cam_extra_5"] = MockStream()
    mock_yolo_batch.side_effect = lambda frames, stream_ids, frame_counters, skip_interval: {
        stream_id: [{"track_id": idx + 1}] for idx, stream_id in enumerate(stream_ids)
    }

    collector = DeadlinedBatchCollector(max_batch_size=2, max_wait_ms=40.0, base_skip_interval=1)
    results = collector.collect_and_process_batch([
        "cam_fast_1",
        "cam_fast_2",
        "cam_fast_3",
        "cam_lagging_4",
        "cam_extra_5",
    ])

    assert mock_yolo_batch.call_count == 3
    called_streams = [stream_id for call in mock_yolo_batch.call_args_list for stream_id in call.kwargs["stream_ids"]]
    assert called_streams == ["cam_fast_1", "cam_fast_2", "cam_fast_3", "cam_lagging_4", "cam_extra_5"]
    assert set(results) == set(called_streams)
