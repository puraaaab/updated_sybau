import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def get_auth_header():
    res = client.post("/api/v1/auth/login", data={"username": "admin", "password": "Admin@123456"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_get_cameras():
    headers = get_auth_header()
    response = client.get("/api/v1/cameras", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_scan_onvif_cameras():
    headers = get_auth_header()
    response = client.post("/api/v1/cameras/scan", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "devices" in data
    assert "count" in data

def test_camera_zones_crud():
    headers = get_auth_header()
    zones_payload = [
        {"type": "restricted", "name": "Entrance Gate", "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]}
    ]
    post_res = client.post("/api/v1/cameras/cam_1/zones", json=zones_payload, headers=headers)
    assert post_res.status_code == 200

    get_res = client.get("/api/v1/cameras/cam_1/zones", headers=headers)
    assert get_res.status_code == 200
    zones = get_res.json()
    assert len(zones) >= 1
    assert zones[0]["name"] == "Entrance Gate"
