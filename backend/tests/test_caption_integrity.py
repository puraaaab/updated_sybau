import pytest
import numpy as np
import time
from backend.ai.captioning.caption_integrity import caption_integrity_validator, CaptionIntegrityValidator

def test_image_caption_integrity_pass():
    # 1. Generate test frame
    frame_a = np.zeros((100, 100, 3), dtype=np.uint8)
    frame_a[10:50, 10:50] = (255, 0, 0)
    
    # 2. Create envelope before request
    image_id_a, env_a = caption_integrity_validator.create_envelope(frame_a, "cam_test_1", "1 car")
    assert image_id_a.startswith("img_")
    assert env_a.camera_id == "cam_test_1"
    assert len(env_a.image_hash) == 64

    # 3. Validate response with matching parameters
    is_valid, reason, env = caption_integrity_validator.validate_and_claim(
        image_id=image_id_a,
        camera_id="cam_test_1",
        frame=frame_a,
        raw_caption="A red car near the gate."
    )
    assert is_valid is True
    assert reason == "PASS"
    assert env.image_id == image_id_a

def test_image_caption_integrity_reject_unknown_id():
    is_valid, reason, env = caption_integrity_validator.validate_and_claim(
        image_id="img_unknown_999",
        camera_id="cam_test_1",
        frame=None,
        raw_caption="Some caption"
    )
    assert is_valid is False
    assert "Unknown or unregistered image_id" in reason

def test_image_caption_integrity_reject_replay_duplicate():
    frame = np.ones((50, 50, 3), dtype=np.uint8) * 120
    img_id, _ = caption_integrity_validator.create_envelope(frame, "cam_test_2", "person")

    # First claim -> PASS
    v1, _, _ = caption_integrity_validator.validate_and_claim(img_id, "cam_test_2", frame, "Person standing")
    assert v1 is True

    # Second claim with same ID -> REJECTED (Replay protection)
    v2, reason, _ = caption_integrity_validator.validate_and_claim(img_id, "cam_test_2", frame, "Person standing")
    assert v2 is False
    assert "Duplicate or replay" in reason

def test_image_caption_integrity_reject_camera_mismatch():
    frame = np.ones((50, 50, 3), dtype=np.uint8) * 200
    img_id, _ = caption_integrity_validator.create_envelope(frame, "cam_alpha", "truck")

    is_valid, reason, _ = caption_integrity_validator.validate_and_claim(img_id, "cam_beta", frame, "White truck")
    assert is_valid is False
    assert "Camera ID mismatch" in reason

def test_image_caption_integrity_reject_pixel_hash_mismatch():
    frame_orig = np.zeros((50, 50, 3), dtype=np.uint8)
    frame_diff = np.ones((50, 50, 3), dtype=np.uint8) * 255
    img_id, _ = caption_integrity_validator.create_envelope(frame_orig, "cam_hash_test")

    is_valid, reason, _ = caption_integrity_validator.validate_and_claim(img_id, "cam_hash_test", frame_diff, "Scene description")
    assert is_valid is False
    assert "Image pixel hash mismatch" in reason
