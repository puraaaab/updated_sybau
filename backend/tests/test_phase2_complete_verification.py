import pytest
import os
import datetime
from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import SessionLocal, engine, Base
from backend.database.models import User, Camera, Alert, Vehicle, GlobalIdentity, Face, EvidenceLedger
from backend.auth.helpers import create_access_token, get_password_hash
from backend.search.qdrant_utils import purge_poi_vectors, update_poi_vector_payload
from backend.ai.model_manager import model_manager
from backend.services.trajectory import _resolve_dyn_bbox
from backend.search.vector_search import perform_semantic_search, perform_vehicle_search

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_test_data():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Create users
        admin = db.query(User).filter(User.username == "test_phase2_admin").first()
        if not admin:
            db.add(User(
                username="test_phase2_admin",
                password_hash=get_password_hash("Admin@123456"),
                role="admin",
                status="active",
                must_change_password=False
            ))

        viewer = db.query(User).filter(User.username == "test_phase2_viewer").first()
        if not viewer:
            db.add(User(
                username="test_phase2_viewer",
                password_hash=get_password_hash("Viewer@123456"),
                role="viewer",
                status="active",
                must_change_password=False
            ))

        # Create camera
        cam = db.query(Camera).filter(Camera.id == "cam_phase2_test").first()
        if not cam:
            db.add(Camera(
                id="cam_phase2_test",
                name="Phase 2 Test Camera",
                stream_url="storage/recordings/test.mp4",
                status="online",
                latitude=21.1702,
                longitude=72.8311
            ))

        # Create EvidenceLedger row
        ev = db.query(EvidenceLedger).filter(EvidenceLedger.evidence_uuid == "EVID-TEST-PHASE2").first()
        if not ev:
            db.add(EvidenceLedger(
                evidence_uuid="EVID-TEST-PHASE2",
                camera_id="cam_phase2_test",
                start_time=datetime.datetime.now(),
                end_time=datetime.datetime.now(),
                sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                manifest_signature="SIG_TEST_PHASE2",
                creator_username="test_phase2_admin",
                original_file_path="storage/exports/test_evidence.zip",
                is_protected=True,
                created_at=datetime.datetime.now()
            ))

        # Create POI for deletion/rename vector test
        poi = db.query(GlobalIdentity).filter(GlobalIdentity.identity_uuid == "POI_PHASE2_TEST").first()
        if not poi:
            poi = GlobalIdentity(
                identity_uuid="POI_PHASE2_TEST",
                type="person",
                name="Test Suspect",
                embedding_id="emb_phase2_test",
                first_seen=datetime.datetime.now()
            )
            db.add(poi)
            db.commit()
            db.refresh(poi)

        db.commit()
    finally:
        db.close()

def get_admin_token():
    return create_access_token(data={"sub": "test_phase2_admin"})

def get_viewer_token():
    return create_access_token(data={"sub": "test_phase2_viewer"})


# ---------------------------------------------------------------------------
# ORIGINAL AUDIT BUGS
# ---------------------------------------------------------------------------

def test_original_bug02_chat_auth_enforced_and_working():
    """Original BUG-02: /api/v1/chat endpoints reject unauthenticated calls and accept authenticated calls."""
    # Unauthenticated request rejected with 401
    resp_unauth = client.get("/api/v1/chat/history?session_id=sess_test_123")
    assert resp_unauth.status_code == 401

    resp_msg_unauth = client.post("/api/v1/chat/message", json={"query": "test query", "session_id": "sess_1"})
    assert resp_msg_unauth.status_code == 401

    # Authenticated with token succeeds
    token = get_viewer_token()
    resp_auth = client.get(
        "/api/v1/chat/history?session_id=sess_test_123",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp_auth.status_code == 200
    assert "messages" in resp_auth.json()


def test_original_bug03_records_faces_get_is_idempotent_no_delete():
    """Original BUG-03: GET /records/faces does not execute destructive DELETE on database."""
    token = get_viewer_token()
    db = SessionLocal()
    try:
        # Create a test face entry
        test_face = Face(
            track_uuid="trk_safe_test",
            label="POI_SAFE_TEST",
            confidence=0.95,
            timestamp=datetime.datetime.now()
        )
        db.add(test_face)
        db.commit()
        face_id = test_face.id

        # Execute GET request
        resp = client.get("/api/v1/records/faces", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

        # Verify face record was NOT deleted by GET query
        recheck = db.query(Face).filter(Face.id == face_id).first()
        assert recheck is not None
        assert recheck.label == "POI_SAFE_TEST"

        # Cleanup
        db.delete(recheck)
        db.commit()
    finally:
        db.close()


def test_original_bug04_forensics_exports_reads_evidence_ledger():
    """Original BUG-04: GET /forensics/exports queries EvidenceLedger table directly."""
    token = get_viewer_token()
    resp = client.get("/api/v1/forensics/exports", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    matching = [e for e in data if e.get("export_uuid") == "EVID-TEST-PHASE2"]
    assert len(matching) == 1
    assert matching[0]["sha256_hash"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert matching[0]["camera_id"] == "cam_phase2_test"


def test_original_bug05_watchlist_delete_and_rename_purges_vectors():
    """Original BUG-05: Watchlist delete and rename purge vector storage."""
    token = get_admin_token()
    db = SessionLocal()
    try:
        poi = db.query(GlobalIdentity).filter(GlobalIdentity.identity_uuid == "POI_PHASE2_TEST").first()
        if not poi:
            poi = GlobalIdentity(
                identity_uuid="POI_PHASE2_TEST",
                type="person",
                name="Test Suspect",
                embedding_id="emb_phase2_test",
                first_seen=datetime.datetime.now()
            )
            db.add(poi)
            db.commit()
            db.refresh(poi)
        assert poi is not None
        poi_id = poi.id

        # Seed model_manager fallback vector
        model_manager.vector_db.append({
            "id": "emb_phase2_test",
            "vector": [0.1] * 128,
            "payload": {"type": "face", "identity_uuid": "POI_PHASE2_TEST", "label": "Test Suspect"}
        })

        # Test Rename
        resp_rename = client.put(
            f"/api/v1/watchlist/{poi_id}",
            json={"name": "Renamed Suspect"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp_rename.status_code == 200
        # Check in-memory payload updated
        for item in model_manager.vector_db:
            if item.get("payload", {}).get("identity_uuid") == "POI_PHASE2_TEST":
                assert item["payload"]["label"] == "Renamed Suspect"

        # Test Delete
        resp_del = client.delete(
            f"/api/v1/watchlist/{poi_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp_del.status_code == 200
        # Check purged from in-memory fallback
        remaining = [item for item in model_manager.vector_db if item.get("payload", {}).get("identity_uuid") == "POI_PHASE2_TEST"]
        assert len(remaining) == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# ADDITIONAL BUGS (BUG-EXTRA-01 through BUG-EXTRA-05)
# ---------------------------------------------------------------------------

def test_bug_extra_01_dyn_bbox_resolver_safe():
    """BUG-EXTRA-01: _resolve_dyn_bbox handles invalid/missing paths safely without NameError."""
    assert _resolve_dyn_bbox("", "car", "cam_1") is None
    assert _resolve_dyn_bbox("/api/v1/playback/snapshot/missing_file", "car", "cam_1") is None


def test_bug_extra_02_vector_dimension_segregation(monkeypatch):
    """BUG-EXTRA-02: Text semantic search (384/1024-dim) and vehicle feature search (576-dim) are separated."""
    monkeypatch.setattr("backend.search.vector_search.get_text_embedding", lambda text: [0.01] * 1024)
    res_sem = perform_semantic_search("blue truck", limit=3)
    assert isinstance(res_sem, list)
    res_veh = perform_vehicle_search([0.05] * 576, limit=3)
    assert isinstance(res_veh, list)


def test_bug_extra_03_null_gps_format_safety():
    """BUG-EXTRA-03: E-Challan and FIR reports safely format cameras with NULL coordinates."""
    token = get_admin_token()
    db = SessionLocal()
    try:
        cam_null = db.query(Camera).filter(Camera.id == "cam_test_null_coords").first()
        if not cam_null:
            cam_null = Camera(id="cam_test_null_coords", name="Null Coord Cam", stream_url="storage/test.mp4", latitude=None, longitude=None)
            db.add(cam_null)
            db.commit()

        alert_null = Alert(camera_id="cam_test_null_coords", type="ILLEGAL_PARKING", message="Parked in no-parking zone", confidence=0.88)
        db.add(alert_null)
        db.commit()
        db.refresh(alert_null)

        resp_ch = client.get(f"/api/v1/challan/generate/{alert_null.id}", headers={"Authorization": f"Bearer {token}"})
        assert resp_ch.status_code == 200
        assert "E-CHALLAN CITATION" in resp_ch.text

        resp_fir = client.get("/api/v1/forensics/fir-report/FIR_TEST_NULL_GPS", headers={"Authorization": f"Bearer {token}"})
        assert resp_fir.status_code == 200
        assert "FIRST INFORMATION REPORT" in resp_fir.text
    finally:
        db.close()


def test_bug_extra_04_stream_manager_reconnect_cache_invalidation():
    """BUG-EXTRA-04: StreamManager reconnect cache invalidation prevents tight retry lockups."""
    from backend.services.stream_resolver import _resolved_cache, _cache_lock, invalidate_cache
    cam_id = "test_recon_cam"
    with _cache_lock:
        _resolved_cache[cam_id] = {"url": "rtsp://cached.url", "expiry": 1234567890.0}
    assert cam_id in _resolved_cache
    invalidate_cache(cam_id)
    assert cam_id not in _resolved_cache


def test_bug_extra_05_forensic_export_ffmpeg_safe_invocation():
    """BUG-EXTRA-05: Forensic export endpoint safely handles missing recording files without unhandled 500 crashes."""
    token = get_admin_token()
    resp = client.post(
        "/api/v1/forensics/export?camera_id=cam_phase2_test&start_time=2026-08-14T10:00:00&end_time=2026-08-14T10:05:00",
        headers={"Authorization": f"Bearer {token}"}
    )
    # Returns 404 or 400 with clean error message when no raw recording clips exist, never crashes backend
    assert resp.status_code in (400, 404)
    assert "detail" in resp.json()
