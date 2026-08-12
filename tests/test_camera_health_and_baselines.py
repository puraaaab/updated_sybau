"""
Test Suite: Camera Health & Tampering Monitor & Adaptive Behavioral Baselines
"""

import pytest
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.connection import Base
from backend.database.models import CameraHealthLog, CameraBaseline, CanonicalEvent, _istnow
from backend.monitoring.camera_health_monitor import CameraHealthMonitor
from backend.ai.behavior.adaptive_baseline import AdaptiveBaselineEngine


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_camera_health_monitor_freeze_and_blur(monkeypatch, in_memory_db):
    """Tests CameraHealthMonitor freeze detection and blur score calculation."""
    monitor = CameraHealthMonitor()

    import backend.monitoring.camera_health_monitor as health_module
    monkeypatch_db = lambda: in_memory_db
    monkeypatch.setattr(health_module, "SessionLocal", monkeypatch_db)

    # 1. Normal sharp frame
    frame = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
    res1 = monitor.analyze_frame("cam_health_test", frame)
    assert res1["status"] in ["ONLINE", "CAMERA_FROZEN", "CAMERA_BLURRY", "CAMERA_DARK"]

    # 2. Fully frozen static black frame repeatedly
    black_frame = np.zeros((200, 200, 3), dtype=np.uint8)
    for _ in range(25):
        res2 = monitor.analyze_frame("cam_health_test", black_frame)

    assert res2["freeze_score"] == 1.0 or res2["dark_score"] > 0.5


def test_adaptive_baseline_anomaly_detection(monkeypatch, in_memory_db):
    """Tests AdaptiveBaselineEngine z-score statistical anomaly calculation."""
    engine_inst = AdaptiveBaselineEngine(z_score_threshold=3.0, min_samples=3)

    import backend.ai.behavior.adaptive_baseline as baseline_module
    monkeypatch_db = lambda: in_memory_db
    monkeypatch.setattr(baseline_module, "SessionLocal", monkeypatch_db)

    # Record 4 normal samples of 2 occupants
    for _ in range(4):
        engine_inst.record_and_evaluate("cam_base_test", current_count=2)

    # Record sudden anomaly of 25 occupants at night -> MUST TRIGGER ANOMALY
    anom = engine_inst.record_and_evaluate("cam_base_test", current_count=25)
    assert anom is not None
    assert anom["event_type"] == "ANOMALOUS_ACTIVITY"
    assert anom["z_score"] >= 3.0
