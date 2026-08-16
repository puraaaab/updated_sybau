import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.database.connection import SessionLocal
from backend.database.models import User, PrivilegeElevationRequest, AuditLog, _istnow
from backend.auth.helpers import create_access_token, get_password_hash

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_elevation_users():
    db: Session = SessionLocal()
    try:
        # Create primary admin
        admin1 = db.query(User).filter(User.username == "admin_elev_1").first()
        if not admin1:
            admin1 = User(
                username="admin_elev_1",
                password_hash=get_password_hash("AdminPass123!"),
                role="admin",
                status="active",
                must_change_password=False
            )
            db.add(admin1)

        # Create secondary admin (for cross-approval testing)
        admin2 = db.query(User).filter(User.username == "admin_elev_2").first()
        if not admin2:
            admin2 = User(
                username="admin_elev_2",
                password_hash=get_password_hash("AdminPass123!"),
                role="admin",
                status="active",
                must_change_password=False
            )
            db.add(admin2)

        # Create operator
        operator = db.query(User).filter(User.username == "operator_elev").first()
        if not operator:
            operator = User(
                username="operator_elev",
                password_hash=get_password_hash("OperatorPass123!"),
                role="operator",
                status="active",
                must_change_password=False
            )
            db.add(operator)
        else:
            operator.role = "operator"

        # Create viewer
        viewer = db.query(User).filter(User.username == "viewer_elev").first()
        if not viewer:
            viewer = User(
                username="viewer_elev",
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
        "admin1_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'admin_elev_1', 'role': 'admin'})}"},
        "admin2_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'admin_elev_2', 'role': 'admin'})}"},
        "operator_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'operator_elev', 'role': 'operator'})}"},
        "viewer_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'viewer_elev', 'role': 'viewer'})}"},
    }


def test_feat02_request_submission_and_rbac(setup_elevation_users):
    op_hdr = setup_elevation_users["operator_headers"]
    
    # 1. Operator submits elevation request
    payload = {
        "requested_role": "admin",
        "reason": "Emergency forensic investigation on restricted evidence vault",
        "ttl_minutes": 30
    }
    res = client.post("/api/v1/elevation/request", json=payload, headers=op_hdr)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "success"
    assert data["request_status"] == "PENDING"
    assert data["requested_role"] == "admin"
    req_uuid = data["request_uuid"]

    # 2. Duplicate pending request is rejected -> 409 Conflict
    res_dup = client.post("/api/v1/elevation/request", json=payload, headers=op_hdr)
    assert res_dup.status_code == 409


def test_feat02_individual_403_checks_for_non_admins_on_review_endpoints(setup_elevation_users):
    viewer_hdr = setup_elevation_users["viewer_headers"]
    op_hdr = setup_elevation_users["operator_headers"]

    # Find the pending request
    db: Session = SessionLocal()
    try:
        req = db.query(PrivilegeElevationRequest).filter(PrivilegeElevationRequest.status == "PENDING").first()
        assert req is not None
        req_uuid = req.request_uuid
    finally:
        db.close()

    # 1. Viewer gets 403 Forbidden on POST /approve
    res = client.post(f"/api/v1/elevation/requests/{req_uuid}/approve", headers=viewer_hdr)
    assert res.status_code == 403, f"Expected 403 for viewer on /approve, got {res.status_code}"

    # 2. Operator gets 403 Forbidden on POST /approve
    res = client.post(f"/api/v1/elevation/requests/{req_uuid}/approve", headers=op_hdr)
    assert res.status_code == 403, f"Expected 403 for operator on /approve, got {res.status_code}"

    # 3. Viewer gets 403 Forbidden on POST /reject
    res = client.post(f"/api/v1/elevation/requests/{req_uuid}/reject", headers=viewer_hdr)
    assert res.status_code == 403, f"Expected 403 for viewer on /reject, got {res.status_code}"

    # 4. Viewer gets 403 Forbidden on POST /revoke
    res = client.post(f"/api/v1/elevation/requests/{req_uuid}/revoke", headers=viewer_hdr)
    assert res.status_code == 403, f"Expected 403 for viewer on /revoke, got {res.status_code}"


def test_feat02_strict_self_approval_prevention(setup_elevation_users):
    admin1_hdr = setup_elevation_users["admin1_headers"]
    admin2_hdr = setup_elevation_users["admin2_headers"]

    # Create a request by admin_elev_1 (or simulate requester = admin1)
    db: Session = SessionLocal()
    try:
        db.query(PrivilegeElevationRequest).filter(PrivilegeElevationRequest.request_uuid == "elev_self_test_01").delete()
        db.commit()

        req = PrivilegeElevationRequest(
            request_uuid="elev_self_test_01",
            username="admin_elev_1",
            requested_role="admin",
            base_role="operator",
            reason="Self-approval security boundary test",
            status="PENDING",
            ttl_minutes=15,
            created_at=_istnow()
        )
        db.add(req)
        db.commit()
    finally:
        db.close()

    # 1. Admin 1 attempts to self-approve their own request -> MUST BE REJECTED 403
    res_self = client.post("/api/v1/elevation/requests/elev_self_test_01/approve", headers=admin1_hdr)
    assert res_self.status_code == 403
    assert "Self-approval is strictly forbidden" in res_self.json()["detail"]

    # 2. Admin 2 (different admin) approves -> SUCCESS 200 OK
    res_peer = client.post("/api/v1/elevation/requests/elev_self_test_01/approve", headers=admin2_hdr)
    assert res_peer.status_code == 200
    assert res_peer.json()["status"] == "success"

    # Verify audit log recorded reviewed_by = admin_elev_2
    db = SessionLocal()
    try:
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.action == "ELEVATION_APPROVED")
            .order_by(AuditLog.timestamp.desc())
            .first()
        )
        assert audit is not None
        assert "admin_elev_2" in audit.username
        assert "admin_elev_1" in audit.detail
    finally:
        db.close()


def test_feat02_ttl_expiration_enforcement_positive_path(setup_elevation_users):
    """
    Positive-path test:
    1. Operator starts with base role 'operator' -> cannot delete cameras/skills.
    2. Admin approves elevation to 'admin' -> operator is now dynamically elevated.
    3. Operator successfully performs admin-only action during active TTL window.
    4. Simulate TTL expiration (expires_at past now).
    5. Operator performs admin action -> rejected with 403 Forbidden because TTL expired!
    """
    op_hdr = setup_elevation_users["operator_headers"]
    admin1_hdr = setup_elevation_users["admin1_headers"]

    # Create fresh elevation request for operator_elev
    db: Session = SessionLocal()
    try:
        # Clean old records for operator_elev
        db.query(PrivilegeElevationRequest).filter(PrivilegeElevationRequest.username == "operator_elev").delete()
        db.commit()

        req = PrivilegeElevationRequest(
            request_uuid="elev_ttl_test_01",
            username="operator_elev",
            requested_role="admin",
            base_role="operator",
            reason="Forensics data export",
            status="PENDING",
            ttl_minutes=10,
            created_at=_istnow()
        )
        db.add(req)
        db.commit()
    finally:
        db.close()

    # 1. Before approval: operator cannot perform admin-only action (e.g. POST /api/v1/skills)
    dummy_skill = {
        "skill_id": "skill_ttl_test",
        "name": "TTL Test Skill",
        "model_name": "dummy",
        "input_type": "frame"
    }
    pre_res = client.post("/api/v1/skills", json=dummy_skill, headers=op_hdr)
    assert pre_res.status_code == 403

    # 2. Admin approves elevation
    approve_res = client.post("/api/v1/elevation/requests/elev_ttl_test_01/approve", headers=admin1_hdr)
    assert approve_res.status_code == 200

    # 3. Check /elevation/status -> verified active elevation
    status_res = client.get("/api/v1/elevation/status", headers=op_hdr)
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["is_elevated"] is True
    assert st_data["effective_role"] == "admin"
    assert st_data["seconds_remaining"] > 0

    # 4. Operator CAN now perform admin action within active TTL window -> 201 Created
    act_res = client.post("/api/v1/skills", json=dummy_skill, headers=op_hdr)
    assert act_res.status_code in [201, 409]

    # Clean up skill
    client.delete("/api/v1/skills/skill_ttl_test", headers=op_hdr)

    # 5. FAST-FORWARD PAST TTL: Simulate expired timestamp in DB
    db = SessionLocal()
    try:
        elev_record = (
            db.query(PrivilegeElevationRequest)
            .filter(PrivilegeElevationRequest.request_uuid == "elev_ttl_test_01")
            .first()
        )
        assert elev_record is not None
        # Set expires_at to 10 seconds in the PAST
        elev_record.expires_at = _istnow() - datetime.timedelta(seconds=10)
        db.commit()
    finally:
        db.close()

    # 6. Operator attempts admin action -> MUST BE REJECTED 403 Forbidden!
    post_exp_res = client.post("/api/v1/skills", json=dummy_skill, headers=op_hdr)
    assert post_exp_res.status_code == 403, f"Expected 403 after TTL expiry, got {post_exp_res.status_code}"

    # 7. Check /elevation/status -> confirms is_elevated is False and role reverted to operator
    post_status = client.get("/api/v1/elevation/status", headers=op_hdr)
    assert post_status.status_code == 200
    assert post_status.json()["is_elevated"] is False
    assert post_status.json()["effective_role"] == "operator"
