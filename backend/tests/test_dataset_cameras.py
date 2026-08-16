import os
import cv2
import pytest
from backend.database.connection import SessionLocal
from backend.database.models import Camera

DATASET_DIR = r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028"

def test_dataset_avi_files_exist_and_readable():
    from backend.scripts.seed_cyber_crime_cams import seed_cyber_crime_dataset_cameras
    seed_cyber_crime_dataset_cameras(force_reseed=True)

    db = SessionLocal()
    cams = db.query(Camera).filter(Camera.id.like("cyber_cam_%")).all()
    assert len(cams) == 8, f"Expected 8 dataset cameras, found {len(cams)}"

    for cam in cams:
        assert os.path.exists(cam.stream_url), f"File missing for camera {cam.name}: {cam.stream_url}"
        cap = cv2.VideoCapture(cam.stream_url)
        assert cap.isOpened(), f"OpenCV failed to open video file: {cam.stream_url}"
        ret, frame = cap.read()
        assert ret and frame is not None, f"Failed to read frame from {cam.stream_url}"
        assert frame.shape[0] > 0 and frame.shape[1] > 0
        cap.release()
    db.close()
