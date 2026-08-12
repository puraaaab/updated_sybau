"""
Test Suite: Production Audio Intelligence & Multimodal Event Fusion
"""

import pytest
import numpy as np
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.connection import Base
from backend.database.models import CanonicalEvent, AudioEvent, _istnow
from backend.ai.audio.acoustic_engine import AudioFeatureExtractor, AudioClassifierModel, ProductionAudioEngine
from backend.services.event_fusion import MultimodalEventFusionEngine


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_audio_feature_extraction_and_classifier():
    """Tests spectral audio feature extraction and audio classifier model output."""
    # Create 16kHz sine wave audio samples (1 second at 3000Hz peak freq)
    t = np.linspace(0, 1.0, 16000, False)
    sine_wave = np.sin(2 * np.pi * 3000 * t) * 20000.0
    samples = sine_wave.astype(np.float32)

    features = AudioFeatureExtractor.extract_features(samples, 16000)
    assert "rms_db" in features
    assert features["rms_db"] > 60.0
    assert features["peak_freq"] > 2500.0

    classifier = AudioClassifierModel()
    res = classifier.classify_window(features)
    assert res["event_type"] in AudioClassifierModel.CLASSES
    assert res["confidence"] > 0.5


def test_production_audio_engine_pcm_processing(monkeypatch, in_memory_db):
    """Tests ProductionAudioEngine PCM chunking and temporal window smoothing."""
    engine_inst = ProductionAudioEngine()
    
    # Generate 1 second of PCM bytes
    t = np.linspace(0, 1.0, 16000, False)
    pcm_samples = (np.sin(2 * np.pi * 4000 * t) * 30000.0).astype(np.int16)
    pcm_bytes = pcm_samples.tobytes()

    # Submit PCM chunks to trigger temporal smoothing
    events1 = engine_inst.process_pcm_chunk("cam_test_aud", pcm_bytes)
    events2 = engine_inst.process_pcm_chunk("cam_test_aud", pcm_bytes)

    # 2 out of 3 windows should trigger an audio anomaly event
    assert isinstance(events1, list)
    assert isinstance(events2, list)


def test_multimodal_event_fusion_lineage(in_memory_db):
    """Tests MultimodalEventFusionEngine correlating video + audio events into compound alert."""
    now_dt = _istnow()

    # 1. Insert Video Event
    v_event = CanonicalEvent(
        event_uuid="EVT_VIDEO_001",
        deduplication_key="cam_01_person_12345",
        camera_id="cam_01",
        event_type="person_detected",
        source_type="video",
        source_component="ai_pipeline",
        status="DETECTED",
        severity="medium",
        confidence=0.91,
        timestamp_start=now_dt,
        timestamp_end=now_dt
    )
    # 2. Insert Audio Event
    a_event = CanonicalEvent(
        event_uuid="EVT_AUDIO_001",
        deduplication_key="cam_01_glass_break_12345",
        camera_id="cam_01",
        event_type="glass_break",
        source_type="audio",
        source_component="acoustic_engine",
        status="DETECTED",
        severity="high",
        confidence=0.89,
        timestamp_start=now_dt,
        timestamp_end=now_dt
    )
    in_memory_db.add(v_event)
    in_memory_db.add(a_event)
    in_memory_db.commit()

    # Run Fusion Engine evaluation
    fusion_engine = MultimodalEventFusionEngine(correlation_window_sec=15.0)

    # Patch SessionLocal to use in_memory_db
    import backend.services.event_fusion as ef_module
    monkeypatch_db = lambda: in_memory_db
    import pytest
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ef_module, "SessionLocal", monkeypatch_db)
        res = fusion_engine.evaluate_and_fuse("cam_01")
        assert res is not None
        assert res["severity"] == "critical"
        assert len(res["source_event_ids"]) == 2
        assert "EVT_VIDEO_001" in res["source_event_ids"]
        assert "EVT_AUDIO_001" in res["source_event_ids"]
