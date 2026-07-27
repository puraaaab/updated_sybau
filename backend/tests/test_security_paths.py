import pytest
from fastapi import HTTPException
from backend.utils.security import safe_join_path

def test_safe_join_path_valid():
    base = "/var/app/storage"
    path = safe_join_path(base, "snapshots", "cam1.jpg")
    assert "snapshots" in path
    assert "cam1.jpg" in path

def test_safe_join_path_traversal_attack():
    base = "/var/app/storage"
    with pytest.raises(HTTPException) as exc_info:
        safe_join_path(base, "..", "..", "etc", "passwd")
    assert exc_info.value.status_code == 400
    assert "path traversal" in exc_info.value.detail.lower()

def test_safe_join_path_absolute_injection():
    base = "/var/app/storage"
    with pytest.raises(HTTPException) as exc_info:
        safe_join_path(base, "/etc/passwd")
    assert exc_info.value.status_code == 400
