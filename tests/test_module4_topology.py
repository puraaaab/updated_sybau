import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import SessionLocal
from backend.database.models import Camera, CameraNode, CameraEdge, User
from backend.auth.helpers import create_access_token, get_password_hash

client = TestClient(app)

@pytest.fixture
def auth_headers():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin_top_test").first()
        if not user:
            user = User(
                username="admin_top_test",
                password_hash=get_password_hash("TestPassword123!"),
                role="admin",
                status="active",
                must_change_password=False
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

    token = create_access_token(data={"sub": "admin_top_test", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}

def test_module4_topology_crud_and_predictive_routing(auth_headers):
    db = SessionLocal()
    try:
        # 1. Ensure test cameras exist
        c1 = db.query(Camera).filter(Camera.id == "cam_top_01").first()
        if not c1:
            db.add(Camera(id="cam_top_01", name="Junction North", stream_url="rtsp://localhost/c1"))
        c2 = db.query(Camera).filter(Camera.id == "cam_top_02").first()
        if not c2:
            db.add(Camera(id="cam_top_02", name="Highway South", stream_url="rtsp://localhost/c2"))
        db.commit()

        # 2. Test GET /api/v1/topology
        res = client.get("/api/v1/topology", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "nodes" in data
        assert "edges" in data
        assert any(n["camera_id"] == "cam_top_01" for n in data["nodes"])

        # 3. Test Drag-and-Drop Node Persistence (PUT /api/v1/topology/nodes/{camera_id})
        update_res = client.put(
            "/api/v1/topology/nodes/cam_top_01",
            json={"map_x": 420.0, "map_y": 380.0, "zone_group": "Sector 4"},
            headers=auth_headers
        )
        assert update_res.status_code == 200
        up_data = update_res.json()
        assert up_data["map_x"] == 420.0
        assert up_data["map_y"] == 380.0

        # Verify node updated in DB
        node = db.query(CameraNode).filter(CameraNode.camera_id == "cam_top_01").first()
        assert node.map_x == 420.0
        assert node.map_y == 380.0

        # 4. Test Create Directed Edge (POST /api/v1/topology/edges)
        edge_res = client.post(
            "/api/v1/topology/edges",
            json={
                "source_camera_id": "cam_top_01",
                "target_camera_id": "cam_top_02",
                "distance_meters": 750.0,
                "expected_transit_sec_min": 60,
                "expected_transit_sec_max": 240,
                "allowed_directions": ["forward"]
            },
            headers=auth_headers
        )
        assert edge_res.status_code == 200
        e_data = edge_res.json()
        assert e_data["source"] == "cam_top_01"
        assert e_data["target"] == "cam_top_02"
        assert e_data["transit_window_sec"] == [60, 240]

        # 5. Verify Edge survives node repositioning!
        client.put(
            "/api/v1/topology/nodes/cam_top_01",
            json={"map_x": 500.0, "map_y": 250.0},
            headers=auth_headers
        )
        edge_in_db = db.query(CameraEdge).filter(
            CameraEdge.source_camera_id == "cam_top_01",
            CameraEdge.target_camera_id == "cam_top_02"
        ).first()
        assert edge_in_db is not None
        assert edge_in_db.expected_transit_sec_min == 60

        # 6. Test Predictive Routing Alert Simulation (POST /api/v1/topology/predict)
        predict_res = client.post(
            "/api/v1/topology/predict",
            json={
                "source_camera_id": "cam_top_01",
                "target_identifier": "GJ05AB9999",
                "target_type": "vehicle",
                "heading_direction": "forward",
                "observed_speed_kmh": 45.0
            },
            headers=auth_headers
        )
        assert predict_res.status_code == 200
        p_data = predict_res.json()
        assert p_data["predicted"] is True
        assert p_data["alerts_count"] >= 1
        assert p_data["alerts"][0]["target_camera_id"] == "cam_top_02"
        assert "expected_window_start" in p_data["alerts"][0]
        assert "expected_window_end" in p_data["alerts"][0]
    finally:
        db.close()
