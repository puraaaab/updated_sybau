import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.database.connection import SessionLocal
from backend.database.models import User, AISkillRegistry, CameraSkillAssignment, EventRule, AuditLog
from backend.auth.helpers import create_access_token, get_password_hash

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_users():
    db: Session = SessionLocal()
    try:
        # Create or update admin user
        admin = db.query(User).filter(User.username == "admin_feat03").first()
        if not admin:
            admin = User(
                username="admin_feat03",
                password_hash=get_password_hash("AdminPass123!"),
                role="admin",
                status="active",
                must_change_password=False
            )
            db.add(admin)

        # Create or update viewer user
        viewer = db.query(User).filter(User.username == "viewer_feat03").first()
        if not viewer:
            viewer = User(
                username="viewer_feat03",
                password_hash=get_password_hash("ViewerPass123!"),
                role="viewer",
                status="active",
                must_change_password=False
            )
            db.add(viewer)

        db.commit()
    finally:
        db.close()

    admin_token = create_access_token({"sub": "admin_feat03", "role": "admin"})
    viewer_token = create_access_token({"sub": "viewer_feat03", "role": "viewer"})
    return {
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
        "viewer_headers": {"Authorization": f"Bearer {viewer_token}"},
    }


def test_feat03_skill_registry_crud_and_rbac(setup_users):
    admin_hdr = setup_users["admin_headers"]
    viewer_hdr = setup_users["viewer_headers"]

    skill_payload = {
        "skill_id": "skill_gunshot_detector",
        "name": "Gunshot & Muzzle Audio/Visual Detector",
        "version": "1.2.0",
        "model_name": "YAMNet-Gunshot-v2",
        "input_type": "audio",
        "output_schema_json": json.dumps({"confidence": "float", "caliber": "string"}),
        "hardware_req": "GPU",
        "min_fps": 1.0,
        "target_fps": 10.0,
        "max_fps": 30.0,
        "is_enabled": True
    }

    # 1. Viewer gets 403 Forbidden on POST /api/v1/skills
    res = client.post("/api/v1/skills", json=skill_payload, headers=viewer_hdr)
    assert res.status_code == 403, f"Expected 403 on POST /skills for viewer, got {res.status_code}"

    # 2. Admin creates skill -> 201 Created (or 409 if exists)
    res = client.post("/api/v1/skills", json=skill_payload, headers=admin_hdr)
    assert res.status_code in [201, 409]

    # 3. Viewer gets 403 Forbidden on PUT /api/v1/skills/{skill_id}
    res = client.put(
        "/api/v1/skills/skill_gunshot_detector",
        json={"target_fps": 20.0},
        headers=viewer_hdr
    )
    assert res.status_code == 403, f"Expected 403 on PUT /skills for viewer, got {res.status_code}"

    # 4. Viewer gets 403 Forbidden on POST /api/v1/skills/assign
    assign_payload = {
        "camera_id": "cam_surat_01",
        "skill_id": "skill_gunshot_detector",
        "config_json": json.dumps({"sensitivity": 0.85})
    }
    res = client.post("/api/v1/skills/assign", json=assign_payload, headers=viewer_hdr)
    assert res.status_code == 403, f"Expected 403 on POST /skills/assign for viewer, got {res.status_code}"

    # 5. Viewer gets 403 Forbidden on DELETE /api/v1/skills/{skill_id}
    res = client.delete("/api/v1/skills/skill_gunshot_detector", headers=viewer_hdr)
    assert res.status_code == 403, f"Expected 403 on DELETE /skills for viewer, got {res.status_code}"

    # 6. Viewer can list skills -> 200 OK
    res = client.get("/api/v1/skills", headers=viewer_hdr)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    found = any(s["skill_id"] == "skill_gunshot_detector" for s in data["items"])
    assert found is True

    # 7. Admin updates skill -> 200 OK
    res = client.put(
        "/api/v1/skills/skill_gunshot_detector",
        json={"target_fps": 15.0, "name": "Gunshot & Blast Detector"},
        headers=admin_hdr
    )
    assert res.status_code == 200

    # 8. Admin assigns skill to camera -> 200 OK
    res = client.post("/api/v1/skills/assign", json=assign_payload, headers=admin_hdr)
    assert res.status_code == 200

    # 9. Viewer lists assignments -> 200 OK
    res = client.get("/api/v1/skills/assignments?camera_id=cam_surat_01", headers=viewer_hdr)
    assert res.status_code == 200
    assigns = res.json()
    assert assigns["total"] >= 1
    assert any(a["skill_id"] == "skill_gunshot_detector" for a in assigns["items"])

    # 10. Cascading delete test: Admin deletes skill -> deletes skill AND unassigns it from all cameras
    del_res = client.delete("/api/v1/skills/skill_gunshot_detector", headers=admin_hdr)
    assert del_res.status_code == 200

    # Confirm skill is gone from registry
    get_res = client.get("/api/v1/skills", headers=viewer_hdr)
    assert not any(s["skill_id"] == "skill_gunshot_detector" for s in get_res.json()["items"])

    # Confirm assignment is gone from camera assignments (cascading delete)
    assign_check = client.get("/api/v1/skills/assignments?camera_id=cam_surat_01", headers=viewer_hdr)
    assert not any(a["skill_id"] == "skill_gunshot_detector" for a in assign_check.json()["items"])


def test_feat03_event_rules_crud_and_rbac(setup_users):
    admin_hdr = setup_users["admin_headers"]
    viewer_hdr = setup_users["viewer_headers"]

    rule_payload = {
        "rule_id": "rule_restricted_night_intrusion",
        "name": "Restricted Zone Night Intrusion Fusion Rule",
        "conditions_json": json.dumps([
            {"type": "zone_entry", "zone_type": "restricted"},
            {"type": "time_range", "start": "22:00", "end": "06:00"}
        ]),
        "actions_json": json.dumps([
            {"type": "alert", "severity": "critical"},
            {"type": "webhook", "target": "https://dispatch.police.gov.in/api/v1/alerts"}
        ]),
        "severity": "critical",
        "cooldown_seconds": 30,
        "is_active": True
    }

    # 1. Viewer gets 403 Forbidden on POST /api/v1/event-rules
    res = client.post("/api/v1/event-rules", json=rule_payload, headers=viewer_hdr)
    assert res.status_code == 403, f"Expected 403 on POST /event-rules for viewer, got {res.status_code}"

    # 2. Admin creates rule -> 201 Created
    res = client.post("/api/v1/event-rules", json=rule_payload, headers=admin_hdr)
    assert res.status_code in [201, 409]

    # 3. Viewer gets 403 Forbidden on PUT /api/v1/event-rules/{rule_id}
    res = client.put(
        "/api/v1/event-rules/rule_restricted_night_intrusion",
        json={"cooldown_seconds": 45},
        headers=viewer_hdr
    )
    assert res.status_code == 403, f"Expected 403 on PUT /event-rules for viewer, got {res.status_code}"

    # 4. Viewer gets 403 Forbidden on DELETE /api/v1/event-rules/{rule_id}
    res = client.delete("/api/v1/event-rules/rule_restricted_night_intrusion", headers=viewer_hdr)
    assert res.status_code == 403, f"Expected 403 on DELETE /event-rules for viewer, got {res.status_code}"

    # 5. Viewer lists rules -> 200 OK
    res = client.get("/api/v1/event-rules", headers=viewer_hdr)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    found = any(r["rule_id"] == "rule_restricted_night_intrusion" for r in data["items"])
    assert found is True

    # 6. Admin updates rule -> 200 OK
    res = client.put(
        "/api/v1/event-rules/rule_restricted_night_intrusion",
        json={"cooldown_seconds": 45, "severity": "high"},
        headers=admin_hdr
    )
    assert res.status_code == 200

    # 7. Admin deletes rule -> 200 OK
    res = client.delete("/api/v1/event-rules/rule_restricted_night_intrusion", headers=admin_hdr)
    assert res.status_code == 200

    # Verify audit log was recorded
    db: Session = SessionLocal()
    try:
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.action == "RULE_DELETED")
            .order_by(AuditLog.timestamp.desc())
            .first()
        )
        assert audit is not None
        assert "rule_restricted_night_intrusion" in audit.detail
    finally:
        db.close()
