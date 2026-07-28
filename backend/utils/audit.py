from typing import Optional
from sqlalchemy.orm import Session
from ..database.models import AuditLog

def log_audit_event(
    db: Session,
    action: str,
    detail: str,
    username: Optional[str] = None,
    ip_address: Optional[str] = None
) -> AuditLog:
    """
    Creates and saves an AuditLog entry in the database.
    """
    entry = AuditLog(
        username=username,
        action=action,
        detail=detail,
        ip_address=ip_address
    )
    db.add(entry)
    db.commit()
    return entry
