import pytest
import numpy as np
import cv2
from backend.ai.privacy.redactor import PrivacyRedactor
from backend.config.service import save_privacy_settings, get_privacy_settings

def test_privacy_redactor_disabled_by_default():
    # Set system settings: privacy disabled
    save_privacy_settings({"enabled": False, "redact_faces": True, "redact_plates": True, "blur_kernel_size": 51})
    
    frame = np.ones((100, 100, 3), dtype=np.uint8) * 128
    detections = [{"class_name": "person", "bbox": [10, 10, 50, 50]}]
    
    redacted = PrivacyRedactor.redact_frame(frame, detections)
    # Since master toggle is False and no override passed, frame remains identical
    assert np.array_equal(frame, redacted)

def test_privacy_redactor_face_only_toggle():
    frame = np.ones((200, 200, 3), dtype=np.uint8) * 200
    # Add random pixel noise to head region so blur produces measurable change
    frame[10:32, 10:100] = np.random.randint(0, 255, (22, 90, 3), dtype=np.uint8)
    
    detections = [
        {"class_name": "person", "bbox": [10, 10, 100, 100]},
        {"class_name": "license_plate", "bbox": [120, 120, 180, 150]}
    ]
    
    # Force mask_faces=True, mask_plates=False
    redacted = PrivacyRedactor.redact_frame(frame, detections, mask_faces=True, mask_plates=False)
    
    # Face area (top portion of person bbox) should be altered
    head_region_original = frame[10:32, 10:100]
    head_region_redacted = redacted[10:32, 10:100]
    assert not np.array_equal(head_region_original, head_region_redacted)
    
    # License plate region should remain untouched
    plate_original = frame[120:150, 120:180]
    plate_redacted = redacted[120:150, 120:180]
    assert np.array_equal(plate_original, plate_redacted)

def test_privacy_redactor_plate_only_toggle():
    frame = np.ones((200, 200, 3), dtype=np.uint8) * 200
    # Add random pixel noise to region so blur produces measurable change
    frame[120:150, 120:180] = np.random.randint(0, 255, (30, 60, 3), dtype=np.uint8)
    
    detections = [
        {"class_name": "person", "bbox": [10, 10, 100, 100]},
        {"class_name": "license_plate", "bbox": [120, 120, 180, 150]}
    ]
    
    # Force mask_faces=False, mask_plates=True
    redacted = PrivacyRedactor.redact_frame(frame, detections, mask_faces=False, mask_plates=True)
    
    # Plate region should be altered by Gaussian blur
    plate_original = frame[120:150, 120:180]
    plate_redacted = redacted[120:150, 120:180]
    assert not np.array_equal(plate_original, plate_redacted)
