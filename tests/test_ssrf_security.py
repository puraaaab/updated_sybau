"""
Test Suite: Anti-TOCTOU SSRF Protection & Path Traversal Security
"""

import pytest
from fastapi import HTTPException
from backend.utils.security import validate_safe_url, is_ip_blocked, safe_join_path


def test_ip_blocked_checks():
    """Verifies that private IPv4, IPv6, loopback, and cloud metadata IPs are blocked."""
    assert is_ip_blocked("127.0.0.1") is True
    assert is_ip_blocked("10.0.0.5") is True
    assert is_ip_blocked("192.168.1.1") is True
    assert is_ip_blocked("169.254.169.254") is True
    assert is_ip_blocked("::1") is True
    assert is_ip_blocked("8.8.8.8") is False


def test_validate_safe_url_ssrf_rejection():
    """Verifies that validate_safe_url rejects forbidden loopback and metadata URLs."""
    with pytest.raises(HTTPException) as exc_info:
        validate_safe_url("http://127.0.0.1/admin")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info2:
        validate_safe_url("http://169.254.169.254/latest/meta-data/")
    assert exc_info2.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info3:
        validate_safe_url("file:///etc/passwd")
    assert exc_info3.value.status_code == 400


def test_path_traversal_protection():
    """Verifies that safe_join_path prevents path traversal attempts."""
    with pytest.raises(HTTPException) as exc_info:
        safe_join_path("/app/storage", "../../etc/passwd")
    assert exc_info.value.status_code == 400


def test_resolve_and_pin_target():
    """Verifies that resolve_and_pin_target validates host and returns pinned IP."""
    from backend.utils.security import resolve_and_pin_target
    val_url, pinned_ip = resolve_and_pin_target("http://google.com")
    assert val_url.startswith("http://google.com")
    assert len(pinned_ip) > 0

