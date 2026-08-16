"""
Unit tests for Abandoned / Unattended Object Detection (Prompt 9.2).
"""
import pytest
from backend.services.detectors.abandoned_object import AbandonedObjectDetector


def test_abandoned_backpack_triggers_alert_after_dwell():
    detector = AbandonedObjectDetector(
        dwell_time_sec=10.0,
        owner_distance_pixels=100.0,
        max_displacement_pixels=20.0,
        alert_cooldown_sec=5.0,
    )

    t0 = 1000.0
    cam_id = "cam_test_station"

    # Frame 1 at t=0s: Backpack detected at (200, 200, 250, 250), person walks away at (500, 500, 550, 600)
    dets_t0 = [
        {"track_id": "bag_01", "class_name": "backpack", "bbox": [200, 200, 250, 250], "confidence": 0.92},
        {"track_id": "person_01", "class_name": "person", "bbox": [500, 500, 550, 600], "confidence": 0.95},
    ]
    alerts_0 = detector.process_frame_detections(cam_id, dets_t0, current_timestamp=t0)
    assert len(alerts_0) == 0  # Not dwelt long enough yet

    # Frame 2 at t=5s: Still stationary, no owner
    alerts_5 = detector.process_frame_detections(cam_id, dets_t0, current_timestamp=t0 + 5.0)
    assert len(alerts_5) == 0

    # Frame 3 at t=12s: Stationary for 12s (> 10s dwell), owner is > 100px away -> Trigger alert!
    alerts_12 = detector.process_frame_detections(cam_id, dets_t0, current_timestamp=t0 + 12.0)
    assert len(alerts_12) == 1
    alert = alerts_12[0]
    assert alert["type"] == "ABANDONED_OBJECT"
    assert alert["track_id"] == "bag_01"
    assert alert["dwell_seconds"] >= 10.0
    assert "Unattended BACKPACK" in alert["details"]


def test_bag_with_owner_nearby_does_not_alert_negative_case():
    # Negative case: Bag is stationary, but owner is sitting right next to it (distance <= 100px)
    detector = AbandonedObjectDetector(
        dwell_time_sec=10.0,
        owner_distance_pixels=100.0,
        max_displacement_pixels=20.0,
    )

    t0 = 2000.0
    cam_id = "cam_test_bench"

    # Person center is at (230, 230), Bag center is at (225, 225) -> distance is < 10px
    attended_dets = [
        {"track_id": "suitcase_01", "class_name": "suitcase", "bbox": [200, 200, 250, 250], "confidence": 0.94},
        {"track_id": "seated_person", "class_name": "person", "bbox": [210, 200, 260, 280], "confidence": 0.96},
    ]

    # Process frame at t=0s, t=10s, t=20s
    detector.process_frame_detections(cam_id, attended_dets, current_timestamp=t0)
    detector.process_frame_detections(cam_id, attended_dets, current_timestamp=t0 + 10.0)
    alerts_20 = detector.process_frame_detections(cam_id, attended_dets, current_timestamp=t0 + 20.0)

    # Must NOT alert because owner is right next to the suitcase
    assert len(alerts_20) == 0


def test_moving_luggage_does_not_trigger_abandoned_alert():
    # Negative case: Bag is moving with someone (displacement > max_displacement_pixels)
    detector = AbandonedObjectDetector(
        dwell_time_sec=10.0,
        owner_distance_pixels=100.0,
        max_displacement_pixels=20.0,
    )

    t0 = 3000.0
    cam_id = "cam_walkway"

    # Frame 1: bag at (100, 100, 150, 150)
    detector.process_frame_detections(cam_id, [{"track_id": "moving_bag", "class_name": "handbag", "bbox": [100, 100, 150, 150]}], current_timestamp=t0)
    # Frame 2: bag moved to (200, 200, 250, 250) at t=6s
    detector.process_frame_detections(cam_id, [{"track_id": "moving_bag", "class_name": "handbag", "bbox": [200, 200, 250, 250]}], current_timestamp=t0 + 6.0)
    # Frame 3: bag moved to (300, 300, 350, 350) at t=12s
    alerts = detector.process_frame_detections(cam_id, [{"track_id": "moving_bag", "class_name": "handbag", "bbox": [300, 300, 350, 350]}], current_timestamp=t0 + 12.0)

    assert len(alerts) == 0
