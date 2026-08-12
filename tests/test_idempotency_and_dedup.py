"""
Test Suite: Canonical Event Contract & Idempotency / Deduplication
"""

import pytest
import datetime
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.connection import Base
from backend.database.models import CanonicalEvent, _istnow


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_canonical_event_contract_and_deduplication(in_memory_db):
    """Verifies that CanonicalEvent stores deduplication keys and parent lineage cleanly."""
    event1_uuid = str(uuid.uuid4())
    dedup_key = "cam_01_restricted_area_17700000"
    now_dt = _istnow()

    event1 = CanonicalEvent(
        event_uuid=event1_uuid,
        deduplication_key=dedup_key,
        camera_id="cam_01",
        event_type="restricted_area_entry",
        source_type="video",
        source_component="ai_pipeline",
        status="DETECTED",
        severity="high",
        confidence=0.92,
        model_name="YOLOv8",
        model_version="v8.0",
        inference_backend="PyTorch/CUDA",
        timestamp_start=now_dt,
        timestamp_end=now_dt
    )
    in_memory_db.add(event1)
    in_memory_db.commit()

    # Query back
    saved = in_memory_db.query(CanonicalEvent).filter(CanonicalEvent.event_uuid == event1_uuid).first()
    assert saved is not None
    assert saved.deduplication_key == dedup_key
    assert saved.status == "DETECTED"
    assert saved.model_name == "YOLOv8"

    # Test Parent Event Lineage for Fused Event
    fused_uuid = str(uuid.uuid4())
    fused_event = CanonicalEvent(
        event_uuid=fused_uuid,
        deduplication_key="fused_cam_01_high_risk_17700000",
        parent_event_id=event1_uuid,
        source_event_ids_json=f'["{event1_uuid}"]',
        camera_id="cam_01",
        event_type="fusion_high_risk",
        source_type="fusion",
        source_component="fusion_engine",
        status="CONFIRMED",
        severity="critical",
        confidence=0.97,
        timestamp_start=now_dt,
        timestamp_end=now_dt
    )
    in_memory_db.add(fused_event)
    in_memory_db.commit()

    fused_saved = in_memory_db.query(CanonicalEvent).filter(CanonicalEvent.event_uuid == fused_uuid).first()
    assert fused_saved is not None
    assert fused_saved.parent_event_id == event1_uuid
    assert fused_saved.status == "CONFIRMED"
