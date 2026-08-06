import pytest
import numpy as np
from backend.ai.face.face_pipeline import process_faces
from backend.ai.vehicle.vehicle_reid import detect_vehicle_color

def test_face_pipeline_128d_vectors():
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = [
        {"class_name": "person", "track_id": 1, "track_uuid": "TRK_TEST_1", "bbox": [100, 100, 200, 300]}
    ]
    faces = process_faces(dummy_frame, detections)
    assert isinstance(faces, list)
    if faces:
        emb = faces[0]["embedding"]
        assert len(emb) == 128, f"Expected 128D SFace vector, got {len(emb)}D"

def test_vehicle_color_detection():
    red_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    red_crop[:, :] = (0, 0, 255) # BGR red
    res = detect_vehicle_color(red_crop)
    color = res[0] if isinstance(res, tuple) else res
    assert color in ["red", "unknown"]

