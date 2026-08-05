import time
import numpy as np
from backend.ai.captioning.captioner import submit_async_scene_caption, FlorenceBatchQueue

def test_async_captioner_submission():
    # Test non-blocking submission
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    success = submit_async_scene_caption(dummy_frame, camera_id="test_cam_1", yolo_summary="1 person")
    assert success is True

def test_florence_batch_queue_async():
    q = FlorenceBatchQueue(max_batch_size=2, max_wait_sec=0.05, max_queue_size=10)
    dummy_frame = np.zeros((50, 50, 3), dtype=np.uint8)
    
    received_captions = []
    def callback(cap, meta):
        received_captions.append((cap, meta))

    submitted = q.submit_async(dummy_frame, callback=callback, metadata={"camera_id": "test_cam_2"})
    assert submitted is True
