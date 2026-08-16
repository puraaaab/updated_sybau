import os
import pytest
import datetime
from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import SessionLocal, engine, Base
from backend.database.models import User, Camera
from backend.auth.helpers import create_access_token, get_password_hash, SECRET_KEY, ALGORITHM

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Create test users
        for uname, role in [("test_viewer", "viewer"), ("test_operator", "operator"), ("test_admin", "admin")]:
            existing = db.query(User).filter(User.username == uname).first()
            if not existing:
                db.add(User(
                    username=uname,
                    password_hash=get_password_hash("TestPass@1234"),
                    role=role,
                    status="active",
                    must_change_password=False
                ))
        db.commit()
    finally:
        db.close()

def get_token(username: str):
    return create_access_token(data={"sub": username})

def test_poi_snapshot_unauthenticated_rejected():
    """SEC-02: POI snapshot must return 401 when no token is supplied."""
    resp = client.get("/api/v1/watchlist/POI_TEST123/snapshot")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

def test_poi_snapshot_authenticated_with_query_token():
    """SEC-02: POI snapshot must accept valid token via query parameter."""
    token = get_token("test_viewer")
    resp = client.get(f"/api/v1/watchlist/POI_TEST123/snapshot?token={token}")
    assert resp.status_code in (200, 404), f"Expected 200/404, got {resp.status_code}"

def test_bwc_live_register_unauthenticated_rejected():
    """SEC-03: BWC live registration must return 401 when unauthenticated."""
    resp = client.post("/api/v1/bwc/live/register?officer_id=OFF-1&badge_number=B-1&device_serial=SN-1")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

def test_bwc_live_register_viewer_rejected_403():
    """SEC-03: BWC live registration must return 403 for viewer role."""
    token = get_token("test_viewer")
    resp = client.post(
        "/api/v1/bwc/live/register?officer_id=OFF-1&badge_number=B-1&device_serial=SN-1",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

def test_bwc_live_register_operator_allowed():
    """SEC-03: BWC live registration must succeed for operator role."""
    token = get_token("test_operator")
    resp = client.post(
        "/api/v1/bwc/live/register?officer_id=OFF-1&badge_number=B-1&device_serial=SN-TEST-LIVE-1",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

def test_media_access_snapshot_unauthenticated_rejected():
    """SEC-01: Playback snapshot must return 401 without auth token."""
    resp = client.get("/api/v1/playback/snapshot/snap_test_123")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

def test_media_access_snapshot_authenticated_allowed():
    """SEC-01: Playback snapshot must succeed with valid token."""
    token = get_token("test_viewer")
    resp = client.get(f"/api/v1/playback/snapshot/snap_test_123?token={token}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

def test_florence_stats_unauthenticated_rejected():
    """Records: Florence stats must return 401 without token."""
    resp = client.get("/api/v1/florence/stats")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

def test_available_range_unauthenticated_rejected():
    """Forensics: Available recording range must return 401 without token."""
    resp = client.get("/api/v1/forensics/available-range?camera_id=cam_1")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

def test_onvif_scan_viewer_rejected_403():
    """Cameras: ONVIF network scan must return 403 for viewer role."""
    token = get_token("test_viewer")
    resp = client.post("/api/v1/cameras/scan", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
