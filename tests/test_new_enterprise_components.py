import pytest
import numpy as np
import os
from unittest.mock import MagicMock


def test_bwc_live_ingest_service():
    from backend.services.bwc_live_ingest import bwc_live_ingest_service
    
    mock_db = MagicMock()
    mock_db.query().filter().first.return_value = None

    result = bwc_live_ingest_service.register_live_bwc(
        db=mock_db,
        officer_id="OFFICER_99",
        badge_number="B9900",
        device_serial="SN_TEST_123",
        lat=21.1738,
        lng=72.8423
    )

    assert result["status"] == "success"
    assert result["camera_id"] == "bwc_live_sn_test_123"
    assert "rtmp://" in result["rtmp_push_url"]
    assert "rtsp://" in result["rtsp_consumer_url"]


def test_person_reid_extractor_512d():
    from backend.ai.person.person_reid import person_reid_extractor
    
    dummy_crop = np.zeros((100, 50, 3), dtype=np.uint8)
    vector = person_reid_extractor.extract_feature(dummy_crop)

    assert len(vector) == 512
    assert isinstance(vector, list)


def test_alpr_deskewing_and_parser():
    from backend.ai.vehicle.alpr_engine import alpr_engine
    
    dummy_plate = np.zeros((30, 100, 3), dtype=np.uint8)
    deskewed = alpr_engine.deskew_plate_crop(dummy_plate)
    assert deskewed is not None

    res = alpr_engine.process_plate(dummy_plate)
    assert "raw_text" in res
    assert "parsed_plate" in res


def test_acoustic_anomaly_detector():
    from backend.ai.audio.acoustic_engine import acoustic_detector
    
    # Generate high amplitude PCM samples (simulating loud noise peak)
    loud_samples = (np.random.randn(16000) * 20000).astype(np.int16).tobytes()
    alerts = acoustic_detector.process_audio_chunk("cam_test", loud_samples)

    assert isinstance(alerts, list)


def test_alert_dispatcher():
    from backend.messaging.dispatch import alert_dispatcher

    sig = alert_dispatcher._compute_hmac_signature('{"test": true}', "secret_key")
    assert isinstance(sig, str)
    assert len(sig) == 64


def test_prometheus_metrics_generator():
    from backend.monitoring.metrics import generate_prometheus_metrics

    metrics_text = generate_prometheus_metrics()
    assert "vms_cpu_utilization_percent" in metrics_text
    assert "vms_active_cameras" in metrics_text
