import pytest
import time
import threading
import numpy as np
from backend.ai.detection import yolo
from backend.ai.model_manager import model_manager

def test_yolo_fallback_concurrency_with_gpu_lock(monkeypatch):
    """
    Tests that multiple threads executing detect_and_track fallback concurrently
    are mutually excluded by model_manager.gpu_lock, so max active workers inside == 1.
    """
    active_workers = 0
    max_concurrent_workers = 0
    worker_lock = threading.Lock()

    def fake_track(*args, **kwargs):
        nonlocal active_workers, max_concurrent_workers
        with worker_lock:
            active_workers += 1
            if active_workers > max_concurrent_workers:
                max_concurrent_workers = active_workers
        
        time.sleep(0.05)
        
        with worker_lock:
            active_workers -= 1
        return []

    class FakeYOLOModel:
        def track(self, *args, **kwargs):
            return fake_track(*args, **kwargs)
        def predict(self, *args, **kwargs):
            return fake_track(*args, **kwargs)

    monkeypatch.setattr(model_manager, "get_yolo", lambda: FakeYOLOModel())

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    threads = []

    def _thread_target():
        yolo.detect_and_track(dummy_frame)

    for _ in range(5):
        t = threading.Thread(target=_thread_target)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=5)

    assert max_concurrent_workers == 1, f"Expected 1 worker at a time under gpu_lock, got {max_concurrent_workers}"
