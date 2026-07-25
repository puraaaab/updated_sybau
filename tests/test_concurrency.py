import pytest
import numpy as np
import threading
from backend.ai.face.face_pipeline import process_faces

def test_concurrent_face_processing():
    """Verify that multiple threads can process faces concurrently without C++ crashes."""
    # Create mock frame (black image)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Mock tracks list
    tracks = [
        {"track_id": 1, "class_name": "person", "label": "person", "bbox": [10, 20, 100, 200], "speed": 1.0}
    ]
    
    exceptions = []
    
    def worker():
        try:
            # Force real face detection run
            res = process_faces(frame, tracks)
            assert isinstance(res, list)
        except Exception as e:
            exceptions.append(e)
            
    threads = [threading.Thread(target=worker) for _ in range(4)]
    
    for t in threads:
        t.start()
        
    for t in threads:
        t.join()
        
    # Verify no threads crashed due to concurrent OpenCV access
    assert len(exceptions) == 0, f"Concurrency crashes detected: {exceptions}"
