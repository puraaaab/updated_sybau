import pytest
from fastapi import HTTPException
from backend.utils.ssrf import validate_proxy_url

def test_validate_proxy_url_valid_https():
    url = "https://manifest.googlevideo.com/api/manifest/hls_playlist/index.m3u8"
    assert validate_proxy_url(url) == url

def test_validate_proxy_url_invalid_scheme():
    with pytest.raises(HTTPException) as exc_info:
        validate_proxy_url("file:///etc/passwd")
    assert exc_info.value.status_code == 400
    assert "scheme" in exc_info.value.detail.lower()

def test_validate_proxy_url_private_ip_loopback():
    with pytest.raises(HTTPException) as exc_info:
        validate_proxy_url("http://127.0.0.1:8000/internal")
    assert exc_info.value.status_code == 403

def test_validate_proxy_url_cloud_metadata():
    with pytest.raises(HTTPException) as exc_info:
        validate_proxy_url("http://169.254.169.254/latest/meta-data/")
    assert exc_info.value.status_code == 403
