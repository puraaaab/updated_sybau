"""
Test Suite: Topology-Constrained OSNet & FastReID Re-Identification & Normalized Journey Events
"""

import pytest
import numpy as np
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.connection import Base
from backend.database.models import (
    GlobalIdentity, PersonJourneyEvent, VehicleJourneyEvent, CameraTopology, _istnow
)
from backend.ai.person.reid_pipeline import OSNetFeatureExtractor, PersonReIDPipeline
from backend.ai.vehicle.vehicle_reid import FastReIDFeatureExtractor, VehicleReIDPipeline


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_osnet_and_fastreid_feature_extractors():
    """Tests OSNet 512D and FastReID 2048D feature vector shapes and normalization."""
    dummy_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    dummy_crop[20:80, 20:80] = [120, 200, 50]

    osnet = OSNetFeatureExtractor()
    emb_person = osnet.extract_embedding(dummy_crop)
    assert len(emb_person) == 512
    assert abs(np.linalg.norm(emb_person) - 1.0) < 1e-3

    fastreid = FastReIDFeatureExtractor()
    emb_vehicle = fastreid.extract_embedding(dummy_crop)
    assert len(emb_vehicle) == 2048
    assert abs(np.linalg.norm(emb_vehicle) - 1.0) < 1e-3


def test_person_reid_pipeline_and_journey_persistence(monkeypatch, in_memory_db):
    """Tests PersonReIDPipeline matching and normalized PersonJourneyEvent database persistence."""
    pipeline = PersonReIDPipeline()

    import backend.ai.person.reid_pipeline as person_reid_module
    monkeypatch_db = lambda: in_memory_db
    monkeypatch.setattr(person_reid_module, "SessionLocal", monkeypatch_db)

    dummy_crop = np.zeros((120, 60, 3), dtype=np.uint8)
    dummy_crop[10:100, 10:50] = [200, 100, 50]

    res1 = pipeline.process_person_track("cam_01", "TRK_101", dummy_crop)
    assert res1 is not None
    assert "global_person_id" in res1
    global_id = res1["global_person_id"]

    # Query normalized journey table
    journey = in_memory_db.query(PersonJourneyEvent).filter(
        PersonJourneyEvent.global_person_id == global_id
    ).first()
    assert journey is not None
    assert journey.camera_id == "cam_01"
    assert journey.track_id == "TRK_101"


def test_vehicle_reid_pipeline_plate_correlation(monkeypatch, in_memory_db):
    """Tests VehicleReIDPipeline with OCR license plate candidate correlation."""
    pipeline = VehicleReIDPipeline()

    import backend.ai.vehicle.vehicle_reid as veh_reid_module
    monkeypatch_db = lambda: in_memory_db
    monkeypatch.setattr(veh_reid_module, "SessionLocal", monkeypatch_db)

    dummy_crop = np.zeros((100, 200, 3), dtype=np.uint8)
    dummy_crop[20:80, 20:180] = [50, 50, 200]

    res1 = pipeline.process_vehicle_track("cam_01", "TRK_V201", dummy_crop, license_plate="KA01MH1234")
    assert res1 is not None
    assert res1["license_plate"] == "KA01MH1234"
    global_v_id = res1["global_vehicle_id"]

    # Match second observation from another camera with same plate
    res2 = pipeline.process_vehicle_track("cam_02", "TRK_V305", dummy_crop, license_plate="KA01MH1234")
    assert res2 is not None
    assert res2["global_vehicle_id"] == global_v_id

    # Verify normalized journey events created for both cameras
    journeys = in_memory_db.query(VehicleJourneyEvent).filter(
        VehicleJourneyEvent.global_vehicle_id == global_v_id
    ).all()
    assert len(journeys) == 2
    cams = [j.camera_id for j in journeys]
    assert "cam_01" in cams
    assert "cam_02" in cams
