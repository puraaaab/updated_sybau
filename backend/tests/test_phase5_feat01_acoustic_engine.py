import base64
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.database.connection import SessionLocal
from backend.database.models import User, AudioEvent, CanonicalEvent
from backend.ai.audio.acoustic_engine import (
    AudioFeatureExtractor,
    AudioClassifierModel,
    ProductionAudioEngine,
    production_audio_engine
)
from backend.auth.helpers import create_access_token, get_password_hash

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_audio_users():
    db: Session = SessionLocal()
    try:
        op = db.query(User).filter(User.username == "operator_audio").first()
        if not op:
            op = User(
                username="operator_audio",
                password_hash=get_password_hash("OperatorPass123!"),
                role="operator",
                status="active",
                must_change_password=False
            )
            db.add(op)

        viewer = db.query(User).filter(User.username == "viewer_audio").first()
        if not viewer:
            viewer = User(
                username="viewer_audio",
                password_hash=get_password_hash("ViewerPass123!"),
                role="viewer",
                status="active",
                must_change_password=False
            )
            db.add(viewer)

        db.commit()
    finally:
        db.close()

    return {
        "operator_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'operator_audio', 'role': 'operator'})}"},
        "viewer_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'viewer_audio', 'role': 'viewer'})}"},
    }


def test_feat01_acoustic_spectral_feature_extraction():
    """Verify mathematical spectral feature extraction on 16kHz PCM audio."""
    sample_rate = 16000
    duration = 1.0
    freq = 2500.0  # 2.5 kHz sine wave
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    samples = (15000.0 * np.sin(2 * np.pi * freq * t)).astype(np.float32)

    features = AudioFeatureExtractor.extract_features(samples, sample_rate)
    assert features["rms_db"] > 60.0
    assert abs(features["peak_freq"] - 2500.0) < 50.0
    assert features["zero_crossing_rate"] > 0.1
    assert features["spectral_centroid"] > 1000.0


def test_feat01_classifier_signatures_and_tuning():
    """
    Verify acoustic classifier tuning:
    - Gunshot: dB > 95, 1000 <= freq <= 3500
    - Glass break: dB > 95, freq > 3500
    - Scream: dB > 80, 2000 <= freq <= 5500
    - Explosion: dB > 95, freq < 1000
    """
    model = AudioClassifierModel()

    # 1. Gunshot signature
    gunshot_res = model.classify_window({"rms_db": 98.0, "peak_freq": 2200.0})
    assert gunshot_res["event_type"] == "gunshot"
    assert gunshot_res["confidence"] >= 0.90

    # 2. Glass break signature
    glass_res = model.classify_window({"rms_db": 96.0, "peak_freq": 4500.0})
    assert glass_res["event_type"] == "glass_break"
    assert glass_res["confidence"] >= 0.85

    # 3. Scream signature
    scream_res = model.classify_window({"rms_db": 84.0, "peak_freq": 3200.0})
    assert scream_res["event_type"] == "scream"
    assert scream_res["confidence"] >= 0.80

    # 4. Explosion signature
    explosion_res = model.classify_window({"rms_db": 102.0, "peak_freq": 400.0})
    assert explosion_res["event_type"] == "explosion"
    assert explosion_res["confidence"] >= 0.90


def test_feat01_temporal_window_smoothing_and_anti_false_positive():
    """
    Anti-false-positive test:
    - 1 isolated short spike (< 500ms) does not trigger confirmation (needs 2 out of 3 windows).
    - Sustained audio (> 1.5s) confirms anomaly and generates an alert.
    """
    engine = ProductionAudioEngine(sample_rate=16000, window_size_sec=1.0)
    camera_id = "cam_audio_test_smoothing"

    # Generate 1 short burst of gunshot audio (0.4s = 6400 samples)
    t_short = np.linspace(0, 0.4, 6400, endpoint=False)
    short_samples = (30000.0 * np.sin(2 * np.pi * 2000.0 * t_short)).astype(np.int16).tobytes()

    # Process short chunk -> insufficient to fill 1 full 1-sec window
    events_short = engine.process_pcm_chunk(camera_id, short_samples)
    assert len(events_short) == 0

    # Generate sustained gunshot audio (2.5s = 40000 samples)
    t_sustained = np.linspace(0, 2.5, 40000, endpoint=False)
    sustained_samples = (30000.0 * np.sin(2 * np.pi * 2000.0 * t_sustained)).astype(np.int16).tobytes()

    events_sustained = engine.process_pcm_chunk(camera_id, sustained_samples)
    assert len(events_sustained) >= 1
    assert events_sustained[0]["event_type"] == "gunshot"


def test_feat01_event_bus_and_database_persistence():
    """Verify AudioEvent and CanonicalEvent records are written to database on acoustic anomaly detection."""
    camera_id = "cam_audio_db_test"
    t = np.linspace(0, 2.0, 32000, endpoint=False)
    # Scream frequency: 3000 Hz at high amplitude
    pcm = (28000.0 * np.sin(2 * np.pi * 3000.0 * t)).astype(np.int16).tobytes()

    events = production_audio_engine.process_pcm_chunk(camera_id, pcm)
    assert len(events) >= 1

    db: Session = SessionLocal()
    try:
        # Verify AudioEvent in PostgreSQL
        aud_record = (
            db.query(AudioEvent)
            .filter(AudioEvent.camera_id == camera_id)
            .order_by(AudioEvent.timestamp.desc())
            .first()
        )
        assert aud_record is not None
        assert aud_record.event_type in ["scream", "gunshot", "loud_noise"]

        # Verify CanonicalEvent in PostgreSQL
        canon_record = (
            db.query(CanonicalEvent)
            .filter(
                CanonicalEvent.camera_id == camera_id,
                CanonicalEvent.source_type == "audio"
            )
            .order_by(CanonicalEvent.timestamp_start.desc())
            .first()
        )
        assert canon_record is not None
        assert canon_record.severity in ["critical", "high"]
    finally:
        db.close()


def test_feat01_audio_endpoints_and_rbac(setup_audio_users):
    """Verify RBAC on audio query and audio chunk ingestion endpoints."""
    op_hdr = setup_audio_users["operator_headers"]
    viewer_hdr = setup_audio_users["viewer_headers"]

    # 1. Viewer gets 403 Forbidden on POST /cameras/{id}/audio-chunk
    res = client.post(
        "/api/v1/cameras/cam_audio_rbac/audio-chunk",
        json={"decibels": 95.0, "frequency_hz": 2200.0, "duration_sec": 1.5},
        headers=viewer_hdr
    )
    assert res.status_code == 403, f"Expected 403 for viewer on audio-chunk ingestion, got {res.status_code}"

    # 2. Operator successfully ingests audio-chunk -> 200 OK
    res = client.post(
        "/api/v1/cameras/cam_audio_rbac/audio-chunk",
        json={"decibels": 96.0, "frequency_hz": 4200.0, "duration_sec": 2.0},
        headers=op_hdr
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["events_detected"] >= 1

    # 3. Viewer can list audio events -> 200 OK
    res_list = client.get("/api/v1/analytics/audio-events?camera_id=cam_audio_rbac", headers=viewer_hdr)
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["total"] >= 1
    assert len(list_data["items"]) >= 1
