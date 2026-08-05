import time
import numpy as np
from backend.ai.captioning.captioner import submit_async_scene_caption, FlorenceRoundRobinScheduler

def test_async_captioner_submission():
    # Test non-blocking submission
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    success = submit_async_scene_caption(dummy_frame, camera_id="test_cam_1", yolo_summary="1 person")
    assert success is True

def test_florence_round_robin_scheduler():
    sched = FlorenceRoundRobinScheduler(dispatch_interval_seconds=0.1)
    dummy_frame = np.zeros((50, 50, 3), dtype=np.uint8)
    
    submitted = sched.register_pending_frame("test_cam_2", dummy_frame, {"camera_id": "test_cam_2"})
    assert submitted is True
    stats = sched.get_stats()
    assert "test_cam_2" in stats.get("active_cameras", []) or "test_cam_2" in stats.get("camera_stats", {})
    sched.stop()

