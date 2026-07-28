import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.connection import Base
from backend.database.models import User, AuditLog, Track
from backend.utils.audit import log_audit_event
from backend.utils.security import safe_join_path
from backend.utils.ssrf import validate_proxy_url

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_user_status_attributes(db_session):
    user = User(
        username="test_operator",
        password_hash="hash123",
        role="operator",
        status="suspended",
        must_change_password=True
    )
    db_session.add(user)
    db_session.commit()

    fetched = db_session.query(User).filter(User.username == "test_operator").first()
    assert fetched.status == "suspended"
    assert fetched.must_change_password is True

def test_audit_log_event_creation(db_session):
    log = log_audit_event(
        db_session,
        action="TEST_ACTION",
        detail="Audit logging integration test",
        username="admin_user"
    )
    assert log.id is not None
    assert log.action == "TEST_ACTION"
    assert log.username == "admin_user"

    logs = db_session.query(AuditLog).all()
    assert len(logs) == 1
    assert logs[0].detail == "Audit logging integration test"

def test_security_helpers():
    from fastapi import HTTPException
    # Test safe_join_path rejection of traversal
    with pytest.raises(HTTPException):
        safe_join_path("/tmp/storage", "../etc/passwd")

    # Test SSRF block on internal loopback
    with pytest.raises(HTTPException):
        validate_proxy_url("http://127.0.0.1:8000/secret")
