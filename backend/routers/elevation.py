"""
VMS Pro — Privilege Elevation Workflow Router (FEAT-02)
Provides time-limited role elevation with strict admin approval, self-approval prevention,
and dynamic TTL-based authorization enforcement.
"""

import uuid
import logging
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import User, PrivilegeElevationRequest, AuditLog, _istnow
from ..auth.helpers import verify_viewer, verify_operator, verify_admin, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/elevation", tags=["Privilege Elevation"])


def _audit(db: Session, username: str, action: str, detail: str):
    try:
        log = AuditLog(
            username=username or "unknown",
            action=action,
            detail=detail,
            timestamp=_istnow()
        )
        db.add(log)
    except Exception as e:
        logger.warning(f"[Audit] Failed to log action {action}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ElevationRequestCreateSchema(BaseModel):
    requested_role: str = Field(default="admin", description="Target role (admin or operator)")
    reason: str = Field(..., min_length=5, max_length=1000, description="Justification for elevation")
    ttl_minutes: int = Field(default=60, ge=5, le=480, description="Duration in minutes (5 to 480)")


class ElevationReviewSchema(BaseModel):
    comment: Optional[str] = Field(default="", max_length=500)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Elevation Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/request", status_code=status.HTTP_201_CREATED)
def submit_elevation_request(
    payload: ElevationRequestCreateSchema,
    current_user: User = Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Submits a request for temporary privilege elevation (RBAC: Viewer+)."""
    if payload.requested_role not in ["admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requested role must be 'admin' or 'operator'."
        )

    base_role = getattr(current_user, "_base_role", current_user.role)
    if base_role == payload.requested_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User already holds the '{base_role}' role."
        )

    # Check for existing PENDING request
    pending = (
        db.query(PrivilegeElevationRequest)
        .filter(
            PrivilegeElevationRequest.username == current_user.username,
            PrivilegeElevationRequest.status == "PENDING"
        )
        .first()
    )
    if pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an active pending elevation request."
        )

    req_uuid = f"elev_{uuid.uuid4().hex[:12]}"
    elev_req = PrivilegeElevationRequest(
        request_uuid=req_uuid,
        username=current_user.username,
        requested_role=payload.requested_role,
        base_role=base_role,
        reason=payload.reason,
        status="PENDING",
        ttl_minutes=payload.ttl_minutes,
        created_at=_istnow()
    )
    db.add(elev_req)
    _audit(
        db,
        current_user.username,
        "ELEVATION_REQUESTED",
        f"User requested elevation to {payload.requested_role} for {payload.ttl_minutes}m. Reason: {payload.reason}"
    )
    db.commit()
    db.refresh(elev_req)

    return {
        "status": "success",
        "request_uuid": elev_req.request_uuid,
        "username": elev_req.username,
        "requested_role": elev_req.requested_role,
        "ttl_minutes": elev_req.ttl_minutes,
        "request_status": elev_req.status
    }


@router.get("/requests")
def list_elevation_requests(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: User = Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """
    Lists elevation requests.
    Admins view all organization requests. Non-admins view only their own requests.
    """
    q = db.query(PrivilegeElevationRequest)

    effective_role = getattr(current_user, "role", "viewer")
    if effective_role != "admin":
        q = q.filter(PrivilegeElevationRequest.username == current_user.username)

    if status_filter:
        q = q.filter(PrivilegeElevationRequest.status == status_filter.upper())

    records = q.order_by(PrivilegeElevationRequest.created_at.desc()).all()
    now = _istnow()

    return {
        "total": len(records),
        "items": [
            {
                "id": r.id,
                "request_uuid": r.request_uuid,
                "username": r.username,
                "base_role": r.base_role,
                "requested_role": r.requested_role,
                "reason": r.reason,
                "status": r.status if not (r.status == "APPROVED" and r.expires_at and r.expires_at <= now) else "EXPIRED",
                "ttl_minutes": r.ttl_minutes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reviewed_by": r.reviewed_by,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "is_active": r.status == "APPROVED" and r.expires_at is not None and r.expires_at > now
            }
            for r in records
        ]
    }


@router.post("/requests/{request_uuid}/approve")
def approve_elevation_request(
    request_uuid: str,
    payload: Optional[ElevationReviewSchema] = None,
    current_admin: User = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """
    Approves a privilege elevation request (RBAC: Admin only).
    STRICT CHECK: Self-approval is strictly forbidden.
    """
    req = db.query(PrivilegeElevationRequest).filter(PrivilegeElevationRequest.request_uuid == request_uuid).first()
    if not req:
        raise HTTPException(status_code=404, detail=f"Elevation request '{request_uuid}' not found.")

    if req.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve request with status '{req.status}'."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # STRICT SELF-APPROVAL PREVENTION TRACE
    # An administrator cannot approve their own elevation request.
    # ─────────────────────────────────────────────────────────────────────────
    if req.username == current_admin.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-approval is strictly forbidden. Another administrator must approve your elevation request."
        )

    now = _istnow()
    req.status = "APPROVED"
    req.reviewed_by = current_admin.username
    req.reviewed_at = now
    req.expires_at = now + datetime.timedelta(minutes=req.ttl_minutes)

    _audit(
        db,
        current_admin.username,
        "ELEVATION_APPROVED",
        f"Admin {current_admin.username} approved elevation for {req.username}: "
        f"base role '{req.base_role}' -> elevated role '{req.requested_role}' for {req.ttl_minutes} minutes. "
        f"Expires at: {req.expires_at.isoformat()}"
    )
    db.commit()
    db.refresh(req)

    return {
        "status": "success",
        "request_uuid": req.request_uuid,
        "username": req.username,
        "effective_role": req.requested_role,
        "expires_at": req.expires_at.isoformat(),
        "ttl_minutes": req.ttl_minutes
    }


@router.post("/requests/{request_uuid}/reject")
def reject_elevation_request(
    request_uuid: str,
    payload: Optional[ElevationReviewSchema] = None,
    current_admin: User = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Rejects an elevation request (RBAC: Admin)."""
    req = db.query(PrivilegeElevationRequest).filter(PrivilegeElevationRequest.request_uuid == request_uuid).first()
    if not req:
        raise HTTPException(status_code=404, detail=f"Elevation request '{request_uuid}' not found.")

    if req.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject request with status '{req.status}'."
        )

    now = _istnow()
    req.status = "REJECTED"
    req.reviewed_by = current_admin.username
    req.reviewed_at = now

    _audit(
        db,
        current_admin.username,
        "ELEVATION_REJECTED",
        f"Admin {current_admin.username} rejected elevation request for {req.username}."
    )
    db.commit()

    return {"status": "success", "request_uuid": req.request_uuid, "request_status": "REJECTED"}


@router.post("/requests/{request_uuid}/revoke")
def revoke_elevation_request(
    request_uuid: str,
    current_admin: User = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Revokes an active approved elevation immediately (RBAC: Admin)."""
    req = db.query(PrivilegeElevationRequest).filter(PrivilegeElevationRequest.request_uuid == request_uuid).first()
    if not req:
        raise HTTPException(status_code=404, detail=f"Elevation request '{request_uuid}' not found.")

    now = _istnow()
    req.status = "REVOKED"
    req.expires_at = now

    _audit(
        db,
        current_admin.username,
        "ELEVATION_REVOKED",
        f"Admin {current_admin.username} revoked active elevation for {req.username}."
    )
    db.commit()

    return {"status": "success", "request_uuid": req.request_uuid, "request_status": "REVOKED"}


@router.get("/status")
def get_elevation_status(
    current_user: User = Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Returns the current effective role and remaining elevation time for the authenticated user."""
    base_role = getattr(current_user, "_base_role", current_user.role)
    effective_role = getattr(current_user, "_effective_role", current_user.role)
    is_active = getattr(current_user, "_elevation_active", False)
    expires_at = getattr(current_user, "_elevation_expires_at", None)

    seconds_remaining = 0
    if is_active and expires_at:
        now = _istnow()
        seconds_remaining = max(0, int((expires_at - now).total_seconds()))

    return {
        "username": current_user.username,
        "base_role": base_role,
        "effective_role": effective_role,
        "is_elevated": is_active,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "seconds_remaining": seconds_remaining
    }
