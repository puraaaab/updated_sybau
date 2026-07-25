"""
Admin-only REST endpoints for:
  - User directory management (list, create, update role/status, soft/hard delete)
  - Audit log viewer with filtering
  - Elevation request queue (placeholder — returns empty list for now)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
import datetime

from ..database.connection import get_db
from ..database.models import User, AuditLog
from ..auth.helpers import verify_admin, get_password_hash

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None


class HardDeleteRequest(BaseModel):
    admin_password: str


# ---------------------------------------------------------------------------
# User Directory
# ---------------------------------------------------------------------------

@router.get("/users")
def list_users(
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user=Depends(verify_admin)
):
    """List all user accounts in the system."""
    users = db.query(User).all()
    result = []
    for u in users:
        result.append({
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "status": getattr(u, "status", "active"),
            "must_change_password": getattr(u, "must_change_password", False),
            "deleted_at": getattr(u, "deleted_at", None),
        })
    return result


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(verify_admin)
):
    """Create a new user account."""
    if body.role not in ["admin", "operator", "viewer", "auditor"]:
        raise HTTPException(status_code=400, detail="Invalid role.")

    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists.")

    new_user = User(
        username=body.username,
        password_hash=get_password_hash(body.password),
        role=body.role,
    )
    db.add(new_user)

    # Write audit log
    db.add(AuditLog(
        username=current_user.username,
        action="USER_CREATE",
        detail=f"Created account '{body.username}' with role '{body.role}'",
    ))
    db.commit()

    return {"message": f"User '{body.username}' created.", "username": body.username, "role": body.role}


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(verify_admin)
):
    """Update role, status, or password for a user."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    changes = []
    if body.role is not None:
        if body.role not in ["admin", "operator", "viewer", "auditor"]:
            raise HTTPException(status_code=400, detail="Invalid role.")
        target.role = body.role
        changes.append(f"role -> {body.role}")

    if body.password is not None:
        target.password_hash = get_password_hash(body.password)
        changes.append("password reset")

    if body.status is not None:
        # Store status in a dynamic attribute (column may not exist on base model)
        # Gracefully handle if column doesn't exist yet
        if hasattr(target, "status"):
            target.status = body.status
        changes.append(f"status -> {body.status}")

    db.add(AuditLog(
        username=current_user.username,
        action="USER_UPDATE",
        detail=f"Updated '{target.username}': {', '.join(changes)}",
    ))
    db.commit()
    return {"message": f"User '{target.username}' updated.", "changes": changes}


@router.delete("/users/{user_id}")
def soft_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(verify_admin)
):
    """Soft-delete a user (marks deleted_at, keeps record)."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    if target.username == current_user.username:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")

    if hasattr(target, "deleted_at"):
        target.deleted_at = datetime.datetime.utcnow()

    db.add(AuditLog(
        username=current_user.username,
        action="USER_SOFT_DELETE",
        detail=f"Soft-deleted account '{target.username}'",
    ))
    db.commit()
    return {"message": f"User '{target.username}' soft-deleted."}


@router.post("/users/{user_id}/hard-delete")
def hard_delete_user(
    user_id: int,
    body: HardDeleteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(verify_admin)
):
    """Permanently erase a user row. Requires admin password confirmation."""
    from ..auth.helpers import verify_password
    if not verify_password(body.admin_password, current_user.password_hash):
        raise HTTPException(status_code=403, detail="Admin password incorrect.")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    if target.username == current_user.username:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")

    username_snapshot = target.username
    db.delete(target)

    db.add(AuditLog(
        username=current_user.username,
        action="USER_HARD_DELETE",
        detail=f"Permanently erased account '{username_snapshot}' from database",
    ))
    db.commit()
    return {"message": f"User '{username_snapshot}' permanently deleted."}


# ---------------------------------------------------------------------------
# Audit Log Viewer
# ---------------------------------------------------------------------------

@router.get("/audit-logs")
def get_audit_logs(
    username: Optional[str] = None,
    action: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    current_user=Depends(verify_admin)
):
    """Retrieve audit log entries with optional filters."""
    query = db.query(AuditLog)

    if username:
        query = query.filter(AuditLog.username.ilike(f"%{username}%"))
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if start:
        try:
            start_dt = datetime.datetime.fromisoformat(start.replace("T", " "))
            query = query.filter(AuditLog.timestamp >= start_dt)
        except ValueError:
            pass
    if end:
        try:
            end_dt = datetime.datetime.fromisoformat(end.replace("T", " "))
            query = query.filter(AuditLog.timestamp <= end_dt)
        except ValueError:
            pass

    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    return [
        {
            "id": log.id,
            "username": log.username or "system",
            "role": "admin",  # Logs don't store role — display placeholder
            "action": log.action,
            "details": log.detail or "",
            "ip_address": log.ip_address,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]


# ---------------------------------------------------------------------------
# Elevation Requests (Placeholder — returns empty list)
# ---------------------------------------------------------------------------

@router.get("/elevation-requests")
def get_elevation_requests(
    db: Session = Depends(get_db),
    current_user=Depends(verify_admin)
):
    """
    Returns pending role-elevation and password-reset requests.
    Currently returns an empty list (feature placeholder).
    """
    return []


@router.post("/elevation-requests/{req_id}/resolve")
def resolve_elevation_request(
    req_id: int,
    action: dict,
    db: Session = Depends(get_db),
    current_user=Depends(verify_admin)
):
    """Resolve an elevation request (approve/reject). Placeholder implementation."""
    return {"message": "No pending elevation requests.", "reset_token": None}
