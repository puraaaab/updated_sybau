import pytest
import os
import datetime
from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import SessionLocal, engine, Base
from backend.database.models import User, Camera, Alert, Vehicle, Track
from backend.auth.helpers import create_access_token, get_password_hash
from backend.services.trajectory import _resolve_dyn_bbox, _parse_bbox_norm
from backend.search.vector_search import perform_semantic_search, perform_vehicle_search

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_phase2_data():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Create operator user
        operator = db.query(User).filter(User.username == "test_phase2_operator").first()
        if not operator:
            db.add(User(
                username="test_phase2_operator",
                password_hash=get_password_hash("Pass@123456"),
                role="operator",
                status="active",
                must_change_password=False
            ))

        # Create camera with NULL coordinates (BUG-04 test case)
        cam_null_gps = db.query(Camera).filter(Camera.id == "cam_null_gps").first()
        if not cam_null_gps:
            db.add(Camera(
                id="cam_null_gps",
                name="Null GPS Camera",
                stream_url="storage/recordings/test.mp4",
                status="online",
                latitude=None,
                longitude=None
            ))

        # Create alert associated with null GPS camera
        alert_test = db.query(Alert).filter(Alert.camera_id == "cam_null_gps").first()
        if not alert_test:
            alert_test = Alert(
                camera_id="cam_null_gps",
                type="SPEEDING",
                message="Vehicle exceeded speed limit",
                severity="high",
                confidence=0.92,
                timestamp=datetime.datetime.now()
            )
            db.add(alert_test)
            db.commit()
            db.refresh(alert_test)

        # Create Vehicle record with null bbox (BUG-01 test case)
        veh = db.query(Vehicle).filter(Vehicle.license_plate == "GJ-05-TEST-99").first()
        if not veh:
            db.add(Vehicle(
                camera_id="cam_null_gps",
                license_plate="GJ-05-TEST-99",
                vehicle_type="car",
                vehicle_color="silver",
                track_uuid="trk_test_null_bbox",
                bbox=None,
                timestamp=datetime.datetime.now()
            ))

        db.commit()
    finally:
        db.close()

def get_operator_token():
    return create_access_token(data={"sub": "test_phase2_operator"})


def test_bug01_dyn_bbox_defined_and_safe():
    """BUG-01: _resolve_dyn_bbox must be defined and return safely without throwing NameError."""
    # Test with non-existent / empty URL
    res = _resolve_dyn_bbox("", "car", "cam_1")
    assert res is None

    # Test with invalid path
    res = _resolve_dyn_bbox("/api/v1/playback/snapshot/nonexistent_file", "person", "cam_1")
    assert res is None

    # Test trajectory endpoint for vehicle with NULL bbox
    token = get_operator_token()
    resp = client.get("/api/v1/forensics/trajectory/GJ-05-TEST-99", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_hits"] >= 1
    assert data["trajectory"][0]["license_plate"] == "GJ-05-TEST-99"


def test_bug03_vector_dimension_query_safe():
    """BUG-03: Vector searches must handle dimensions without mismatch exceptions."""
    # Text semantic search
    res = perform_semantic_search("white car speeding", limit=5)
    assert isinstance(res, list)

    # 576-dim vehicle feature search
    dummy_veh_vector = [0.01] * 576
    res_v = perform_vehicle_search(dummy_veh_vector, limit=5)
    assert isinstance(res_v, list)


def test_bug04_challan_generation_with_null_gps():
    """BUG-04: E-Challan generation must not crash when camera latitude/longitude is NULL."""
    token = get_operator_token()
    db = SessionLocal()
    try:
        alert = db.query(Alert).filter(Alert.camera_id == "cam_null_gps").first()
        assert alert is not None
        resp = client.get(f"/api/v1/challan/generate/{alert.id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "E-CHALLAN CITATION" in resp.text
    finally:
        db.close()


def test_bug04_fir_report_with_null_gps():
    """BUG-04: FIR Report generation must not crash when camera latitude/longitude is NULL."""
    token = get_operator_token()
    resp = client.get("/api/v1/forensics/fir-report/TESTCASE123", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "FIRST INFORMATION REPORT" in resp.text
