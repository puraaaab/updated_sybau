import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.main import app
from backend.utils.security import safe_join_path
from backend.utils.ssrf import validate_proxy_url
from backend.auth.router import _clear_attempts

client = TestClient(app)

def test_path_traversal_prevention():
    base_dir = "/tmp/vms_storage"
    
    # Valid relative subpaths should succeed
    valid_path = safe_join_path(base_dir, "cam_1", "clip_100.mp4")
    assert "clip_100.mp4" in valid_path
    
    # Traversal attempts escaping base_dir MUST raise 400
    with pytest.raises(HTTPException) as exc_info:
        safe_join_path(base_dir, "../../etc/passwd")
    assert exc_info.value.status_code == 400

def test_ssrf_proxy_validation():
    # Valid external HTTPS stream
    assert validate_proxy_url("https://google.com/robots.txt") == "https://google.com/robots.txt"
    
    # Block internal loopback
    with pytest.raises(HTTPException) as exc1:
        validate_proxy_url("http://127.0.0.1:8000/internal")
    assert exc1.value.status_code == 403
    
    # Block cloud metadata
    with pytest.raises(HTTPException) as exc2:
        validate_proxy_url("http://169.254.169.254/latest/meta-data")
    assert exc2.value.status_code == 403
    
    # Block RFC 1918 private network
    with pytest.raises(HTTPException) as exc3:
        validate_proxy_url("http://192.168.1.1/admin")
    assert exc3.value.status_code == 403

def test_login_rate_limiting_lockout():
    test_ip = "192.0.2.45" # RFC 5737 documentation IP
    _clear_attempts(test_ip)
    
    headers = {"X-Forwarded-For": test_ip}
    
    # Send 10 failed login attempts
    for _ in range(10):
        res = client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "BadPassword123!"},
            headers=headers
        )
        assert res.status_code in (401, 429)
        
    # The 11th attempt MUST trigger 429 Too Many Requests
    lockout_res = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "BadPassword123!"},
        headers=headers
    )
    assert lockout_res.status_code == 429
    assert "Too many failed login attempts" in lockout_res.json()["detail"]
    
    # Cleanup after test
    _clear_attempts(test_ip)
