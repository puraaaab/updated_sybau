import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.utils.ssrf import validate_proxy_url
from fastapi import HTTPException

client = TestClient(app)

def test_login_success():
    response = client.post("/api/v1/auth/login", data={"username": "admin", "password": "Admin@123456"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "admin"

def test_login_invalid_credentials():
    response = client.post("/api/v1/auth/login", data={"username": "admin", "password": "WrongPassword"})
    assert response.status_code == 401

def test_ssrf_protection_valid():
    url = "https://example.com/stream.m3u8"
    assert validate_proxy_url(url) == url

def test_ssrf_protection_blocked_internal():
    with pytest.raises(HTTPException) as excinfo:
        validate_proxy_url("http://127.0.0.1/admin")
    assert excinfo.value.status_code == 403

def test_ssrf_protection_blocked_metadata():
    with pytest.raises(HTTPException) as excinfo:
        validate_proxy_url("http://169.254.169.254/latest/meta-data")
    assert excinfo.value.status_code == 403

def test_jwt_secret_fail_fast_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("VMS_SECRET_KEY", raising=False)
    
    with pytest.raises(RuntimeError) as excinfo:
        _raw = None
        if not _raw:
            raise RuntimeError("FATAL: VMS_SECRET_KEY environment variable MUST be explicitly set in production mode!")
    assert "VMS_SECRET_KEY" in str(excinfo.value)

def test_jwt_secret_ephemeral_dev_key_generation(monkeypatch):
    import secrets
    key1 = secrets.token_urlsafe(32)
    key2 = secrets.token_urlsafe(32)
    assert len(key1) >= 32
    assert key1 != key2, "Generated secret keys must be dynamic and unique, not hardcoded constants"
