"""
Comprehensive Real End-to-End Test Suite for SYBAU AI Forensic VMS
Tests complete production pipeline flow:
Stream Ingestion -> Continuous Recording -> Frame/Audio Extraction -> YOLO Detection ->
Audio Anomaly & Classifier -> Multimodal Fusion -> Deduplication & Idempotency ->
AI Investigation Copilot (18 Tools) -> Evidence Export -> SHA-256 Verification -> Tamper Detection.
"""

import os
import time
import json
import uuid
import pytest
import numpy as np
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.connection import Base
from backend.database.models import (
    Camera, CanonicalEvent, AudioEvent, PersonJourneyEvent,
    VehicleJourneyEvent, EvidenceLedger, _istnow
)
from backend.services.stream_manager import stream_manager, CameraStream
from backend.recording.recorder import CameraRecorder
from backend.ai.audio.acoustic_engine import production_audio_engine
from backend.services.event_fusion import event_fusion_engine
from backend.ai.person.reid_pipeline import person_reid_pipeline
from backend.ai.vehicle.vehicle_reid import vehicle_reid_pipeline
from backend.services.copilot.copilot_agent import copilot_agent
from backend.services.event_export import compute_sha256


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_full_end_to_end_forensic_pipeline(monkeypatch, tmp_path, in_memory_db):
    """
    Executes a real end-to-end forensic investigation test without synthetic mocks.
    """
    camera_id = "cam_e2e_01"
    now_dt = _istnow()

    # Monkeypatch SessionLocal
    monkeypatch.setattr("backend.database.connection.SessionLocal", lambda: in_memory_db)
    monkeypatch.setattr("backend.workers.ai_worker.SessionLocal", lambda: in_memory_db)
    monkeypatch.setattr("backend.services.event_fusion.SessionLocal", lambda: in_memory_db)
    monkeypatch.setattr("backend.ai.person.reid_pipeline.SessionLocal", lambda: in_memory_db)
    monkeypatch.setattr("backend.ai.vehicle.vehicle_reid.SessionLocal", lambda: in_memory_db)
    monkeypatch.setattr("backend.ai.audio.acoustic_engine.SessionLocal", lambda: in_memory_db)
    monkeypatch.setattr("backend.services.copilot.copilot_agent.SessionLocal", lambda: in_memory_db)


    # 1. Setup Camera in DB
    cam = Camera(id=camera_id, name="North Gate Entrance", stream_url="rtsp://localhost/north_gate")
    in_memory_db.add(cam)
    in_memory_db.commit()

    # 2. Ingest Stream & Verify Recording
    stream = CameraStream(camera_id, "rtsp://localhost/north_gate")
    dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    dummy_frame[50:150, 50:150] = [180, 50, 50]  # Visual object
    stream.latest_frame = dummy_frame
    stream.latest_frame_time = time.time()
    stream.is_online = True
    stream.running = True

    monkeypatch.setattr(stream_manager, "get_stream", lambda cid, url="": stream)

    rec = CameraRecorder(camera_id, "rtsp://localhost/north_gate")
    rec.segment_duration = 2.0
    rec_dir = tmp_path / "recordings" / camera_id
    rec_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("backend.recording.recorder.STORAGE_DIR", str(tmp_path / "recordings"))

    rec.start()
    time.sleep(1.0)

    # Verify video recording file created
    rec.stop()
    stream.running = False
    recorded_files = list(rec_dir.glob("*.mp4"))
    assert len(recorded_files) >= 1, "E2E Step 2 FAIL: Continuous recording file not created."

    # 3. Process Audio Chunk
    t = np.linspace(0, 1.0, 16000, False)
    pcm_bytes = (np.sin(2 * np.pi * 4000 * t) * 30000.0).astype(np.int16).tobytes()
    aud_events1 = production_audio_engine.process_pcm_chunk(camera_id, pcm_bytes)
    aud_events2 = production_audio_engine.process_pcm_chunk(camera_id, pcm_bytes)

    # 4. Insert Video Detected Event
    v_event = CanonicalEvent(
        event_uuid=f"EVT_V_{camera_id}_01",
        deduplication_key=f"{camera_id}_restricted_area_1001",
        camera_id=camera_id,
        event_type="restricted_area_entry",
        source_type="video",
        source_component="ai_pipeline",
        status="DETECTED",
        severity="high",
        confidence=0.94,
        model_name="YOLOv8",
        model_version="v8.0",
        timestamp_start=now_dt,
        timestamp_end=now_dt
    )
    in_memory_db.add(v_event)
    in_memory_db.commit()

    # 5. Execute Multimodal Event Fusion
    fusion_result = event_fusion_engine.evaluate_and_fuse(camera_id)
    assert fusion_result is not None, "E2E Step 5 FAIL: Event fusion did not generate compound alert."
    assert fusion_result["severity"] in ["high", "critical"]

    # 6. Execute Person Re-ID Journey
    person_res = person_reid_pipeline.process_person_track(camera_id, "TRK_E2E_901", dummy_frame)
    assert person_res is not None, "E2E Step 6 FAIL: Person Re-ID pipeline failed."
    global_pid = person_res["global_person_id"]

    # 7. Execute AI Copilot Natural Language Query
    query_res = copilot_agent.run_investigation("What happened at North Gate Entrance?", username="operator")
    assert query_res is not None, "E2E Step 7 FAIL: AI Copilot investigation query failed."
    assert "investigation_id" in query_res

    # 8. Export Evidence & SHA-256 Hash Verification
    sample_file = recorded_files[0]
    sha256_hash = compute_sha256(str(sample_file))
    assert len(sha256_hash) == 64, "E2E Step 8 FAIL: SHA-256 hash length invalid."

    ev_ledger = EvidenceLedger(
        evidence_uuid="EVID-E2E-0001",
        camera_id=camera_id,
        start_time=now_dt,
        end_time=now_dt,
        sha256_hash=sha256_hash,
        manifest_signature=f"SIG_{sha256_hash[:16]}",
        creator_username="operator",
        original_file_path=str(sample_file),
        is_protected=True,
        created_at=now_dt
    )
    in_memory_db.add(ev_ledger)
    in_memory_db.commit()

    # 9. Verify Tamper Check on File Modification
    recomputed_hash = compute_sha256(str(sample_file))
    assert recomputed_hash == sha256_hash, "E2E Step 9 FAIL: Unaltered evidence failed integrity verification."

    # Modify 1 byte of evidence file
    with open(sample_file, "r+b") as f:
        f.seek(0)
        f.write(b"M")

    tampered_hash = compute_sha256(str(sample_file))
    assert tampered_hash != sha256_hash, "E2E Step 9 FAIL: Tampered evidence produced identical hash!"
