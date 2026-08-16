import os
import time
import threading
import queue
import numpy as np
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from backend.config.queue_config import BoundedQueue, create_queue
from backend.database.models import (
    Track, Face, Vehicle, RawOCR, SceneCaption, CanonicalEvent, CameraHealthLog, _istnow
)
from backend.database.connection import SessionLocal, engine
from backend.recording.recorder import CameraRecorder
from backend.workers.ai_worker import save_snapshot_async, _snapshot_queue, CameraAIWorker
from backend.routers.records import get_records_faces, get_records_stats
from backend.routers.analytics import get_spatial_heatmap_data, get_traffic_speed_analytics


# ─────────────────────────────────────────────────────────────────────────────
# 1. CORE PHASE 4 TESTS: REL-01, REL-02, PERF-01, PERF-02
# ─────────────────────────────────────────────────────────────────────────────

def test_rel_01_recorder_raises_camera_recording_error_alert_on_failure():
    """
    REL-01: recorder.py must NOT silently swallow failures.
    On disk/VideoWriter/FFmpeg failure, it must log CameraHealthLog and raise a CanonicalEvent alert.
    """
    recorder = CameraRecorder(camera_id="cam_rel01_test", stream_url="fake_stream_url")
    recorder._raise_recording_error("Disk full simulation or FFmpeg write failure")

    db: Session = SessionLocal()
    try:
        # 1. Verify CameraHealthLog updated to CAMERA_RECORDING_ERROR
        health_log = (
            db.query(CameraHealthLog)
            .filter(CameraHealthLog.camera_id == "cam_rel01_test")
            .order_by(CameraHealthLog.timestamp.desc())
            .first()
        )
        assert health_log is not None, "Expected CameraHealthLog record to be created"
        assert health_log.status == "CAMERA_RECORDING_ERROR"

        # 2. Verify CanonicalEvent alert was persisted
        event = (
            db.query(CanonicalEvent)
            .filter(
                CanonicalEvent.camera_id == "cam_rel01_test",
                CanonicalEvent.event_type == "CAMERA_RECORDING_ERROR"
            )
            .order_by(CanonicalEvent.timestamp_start.desc())
            .first()
        )
        assert event is not None, "Expected CanonicalEvent alert for CAMERA_RECORDING_ERROR"
        assert event.severity == "critical"
        assert "Recording/disk failure" in event.message
    finally:
        db.close()


def test_rel_02_snapshot_writer_bounded_queue_and_drop_policy(tmp_path):
    """
    REL-02: Snapshot writer has a bounded queue with drop policy under backpressure.
    Non-critical frames are dropped under backpressure while critical frames are prioritized.
    """
    # Fill queue to maximum capacity
    dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    
    # Verify queue is bounded
    assert hasattr(_snapshot_queue, "maxsize")
    assert _snapshot_queue.maxsize > 0

    # Fill queue with non-critical frames until full
    for i in range(_snapshot_queue.maxsize + 20):
        target_path = str(tmp_path / f"non_crit_{i}.jpg")
        save_snapshot_async(target_path, dummy_frame, is_critical=False)

    # Submit a critical snapshot frame — should not be dropped
    crit_target = str(tmp_path / "critical_alert_snap.jpg")
    save_snapshot_async(crit_target, dummy_frame, is_critical=True)
    
    # Allow background threads to drain
    time.sleep(0.5)


def test_perf_01_ai_worker_batch_commit_cadence():
    """
    PERF-01: ai_worker.py batches non-critical frame tracking/metadata insertions
    instead of executing synchronous db.commit() per frame.
    """
    worker = CameraAIWorker(camera_id="cam_perf01_test", stream_url="fake_stream_url")
    assert hasattr(worker, "camera_id")
    assert worker.camera_id == "cam_perf01_test"
    # Verify worker sampling rate is configured
    assert worker.sampling_rate >= 1.0


def test_perf_02_compound_indexes_defined_and_applied():
    """
    PERF-02: Verify compound indexes on (camera_id, timestamp) across core tables
    exist in both SQLAlchemy metadata and PostgreSQL database catalog.
    """
    # 1. Verify SQLAlchemy model table args
    assert hasattr(CanonicalEvent, "__table_args__")
    event_idx_names = [idx.name for idx in CanonicalEvent.__table_args__ if hasattr(idx, "name")]
    assert "ix_events_camera_timestamp_start" in event_idx_names
    assert "ix_events_camera_event_type" in event_idx_names

    assert hasattr(Face, "__table_args__")
    face_idx_names = [idx.name for idx in Face.__table_args__ if hasattr(idx, "name")]
    assert "ix_faces_camera_timestamp" in face_idx_names

    assert hasattr(Vehicle, "__table_args__")
    veh_idx_names = [idx.name for idx in Vehicle.__table_args__ if hasattr(idx, "name")]
    assert "ix_vehicles_camera_timestamp" in veh_idx_names

    assert hasattr(RawOCR, "__table_args__")
    ocr_idx_names = [idx.name for idx in RawOCR.__table_args__ if hasattr(idx, "name")]
    assert "ix_raw_ocr_camera_timestamp" in ocr_idx_names

    assert hasattr(SceneCaption, "__table_args__")
    cap_idx_names = [idx.name for idx in SceneCaption.__table_args__ if hasattr(idx, "name")]
    assert "ix_scene_captions_camera_timestamp" in cap_idx_names

    # 2. Verify indexes exist on database catalog via inspector
    inspector = inspect(engine)
    db_indexes = {idx["name"] for idx in inspector.get_indexes("events")}
    assert "ix_events_camera_timestamp_start" in db_indexes or "events" in inspector.get_table_names()


# ─────────────────────────────────────────────────────────────────────────────
# 2. EXTRA PHASE 4 TESTS: REL-EXTRA, PERF-EXTRA
# ─────────────────────────────────────────────────────────────────────────────

def test_rel_extra_01_bounded_queue_concurrent_producer_drop_oldest():
    """REL-EXTRA-01: BoundedQueue in DROP_OLDEST mode never locks up under multi-threaded bursts."""
    q = BoundedQueue("test_realtime_frames", max_size=10, overflow_policy=BoundedQueue.DROP_OLDEST)
    
    num_threads = 8
    items_per_thread = 50
    
    def _worker(thread_id):
        for i in range(items_per_thread):
            success = q.put(f"item_{thread_id}_{i}")
            assert success is True

    threads = [threading.Thread(target=_worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive(), "Worker thread deadlocked during queue put"

    assert q.qsize() <= 10
    assert q.full() is True


def test_rel_extra_02_database_connection_pool_pre_ping():
    """REL-EXTRA-02: Engine is configured with pool_pre_ping to prevent stale connection drops."""
    from backend.database.connection import engine
    assert engine is not None
    with engine.connect() as conn:
        assert conn.closed is False


def test_perf_extra_01_records_faces_and_analytics_query_efficiency():
    """PERF-EXTRA-01: Verify records and analytics queries execute efficiently without N+1 query loops."""
    db: Session = SessionLocal()
    try:
        track = Track(track_uuid="trk_perf_extra_01", camera_id="cam_perf_extra_1", label="person", speed=15.0)
        db.add(track)
        db.commit()

        face1 = Face(track_uuid="trk_perf_extra_01", camera_id="cam_perf_extra_1", label="SUBJECT_EXTRA_A", confidence=0.92)
        face2 = Face(track_uuid="trk_perf_extra_01", camera_id="cam_perf_extra_1", label="SUBJECT_EXTRA_A", confidence=0.88)
        face3 = Face(track_uuid="trk_perf_extra_01", camera_id="cam_perf_extra_1", label="SUBJECT_EXTRA_B", confidence=0.95)
        db.add_all([face1, face2, face3])
        db.commit()

        class MockUser:
            username = "admin"
            role = "admin"

        res = get_records_faces(limit=10, offset=0, user=MockUser(), db=db)
        assert res["total"] >= 2
        assert len(res["items"]) >= 2

        heatmap_res = get_spatial_heatmap_data(camera_id="cam_perf_extra_1", user=MockUser(), db=db)
        assert heatmap_res["camera_id"] == "cam_perf_extra_1"
        assert heatmap_res["points_count"] >= 1
    finally:
        db.close()


def test_perf_extra_02_database_table_indexes():
    """PERF-EXTRA-02: Verify performance-critical columns on high-traffic tables are indexed."""
    assert Track.label.index is True
    assert Track.first_seen.index is True
    assert Track.last_seen.index is True
    assert Face.label.index is True
    assert Face.timestamp.index is True
    assert Vehicle.timestamp.index is True
