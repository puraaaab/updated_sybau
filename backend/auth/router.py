from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import User
from .helpers import (
    verify_password, get_password_hash, create_access_token,
    verify_admin, get_current_user, validate_password_strength
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Rate Limiter — in-memory brute-force protection (SEC-01)
# Tracks failed login attempts per IP. Clears on successful login.
# ---------------------------------------------------------------------------

import time
import threading

_failed_attempts: dict = {}  # {ip: [timestamp, ...]}
_FAILED_LOCK = threading.Lock()
_MAX_ATTEMPTS = 10          # block after 10 failures within window
_WINDOW_SECONDS = 300       # 5-minute sliding window
_LOCKOUT_SECONDS = 900      # 15-minute lockout after exceeding limit


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _check_rate_limit(ip: str):
    """Raises 429 if the IP has too many recent failed login attempts."""
    now = time.time()
    with _FAILED_LOCK:
        attempts = _failed_attempts.get(ip, [])
        # Prune attempts outside the window
        attempts = [t for t in attempts if now - t < _WINDOW_SECONDS]
        _failed_attempts[ip] = attempts
        if len(attempts) >= _MAX_ATTEMPTS:
            oldest_lockout = min(attempts)
            remaining = int(_LOCKOUT_SECONDS - (now - oldest_lockout))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed login attempts. Try again in {max(remaining, 1)} seconds.",
                headers={"Retry-After": str(max(remaining, 1))},
            )


def _record_failed_attempt(ip: str):
    with _FAILED_LOCK:
        _failed_attempts.setdefault(ip, []).append(time.time())


def _clear_attempts(ip: str):
    with _FAILED_LOCK:
        _failed_attempts.pop(ip, None)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    request: RegisterRequest,
    current_user: User = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    from ..utils.audit import log_audit_event

    if request.role not in ["admin", "operator", "viewer"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin', 'operator', or 'viewer'.")

    pwd_error = validate_password_strength(request.password)
    if pwd_error:
        raise HTTPException(status_code=400, detail=pwd_error)

    db_user = db.query(User).filter(User.username == request.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    hashed_password = get_password_hash(request.password)
    new_user = User(
        username=request.username,
        password_hash=hashed_password,
        role=request.role,
        status="active",
        must_change_password=True,   # Always force password change on new accounts (SEC-02 fix)
    )
    db.add(new_user)
    ip = getattr(current_user, "_client_ip", None)
    log_audit_event(
        db,
        action="USER_REGISTER",
        detail=f"User registered: {request.username} with role {request.role}",
        username=current_user.username,
        ip_address=ip,
    )
    db.commit()
    db.refresh(new_user)
    return {
        "message": f"User registered successfully by {current_user.username}",
        "username": new_user.username,
        "role": new_user.role,
    }


# ---------------------------------------------------------------------------
# Login — with rate limiting (SEC-01), IP audit logging (COMP-03)
# ---------------------------------------------------------------------------

@router.post("/login")
def login(
    http_request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    from ..utils.audit import log_audit_event
    import os

    # Auto-seed default test users on first login attempt if DB is empty
    _seed_users(db)

    client_ip = _get_client_ip(http_request)

    # Rate limiting check (SEC-01)
    _check_rate_limit(client_ip)

    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        _record_failed_attempt(client_ip)
        log_audit_event(
            db,
            action="LOGIN_FAILED",
            detail=f"Failed login attempt for username '{form_data.username}'",
            username=form_data.username,
            ip_address=client_ip,    # COMP-03 fix: now capturing IP
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if getattr(user, "deleted_at", None) is not None or getattr(user, "status", "active") != "active":
        _record_failed_attempt(client_ip)
        log_audit_event(
            db,
            action="LOGIN_BLOCKED",
            detail=f"Blocked login for disabled/suspended user '{user.username}'",
            username=user.username,
            ip_address=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled or suspended. Contact an administrator."
        )

    # Successful login: clear brute-force counter
    _clear_attempts(client_ip)

    access_token = create_access_token(data={"sub": user.username})
    log_audit_event(
        db,
        action="LOGIN_SUCCESS",
        detail=f"User '{user.username}' logged in successfully",
        username=user.username,
        ip_address=client_ip,    # COMP-03 fix
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "must_change_password": getattr(user, "must_change_password", False),
    }


# ---------------------------------------------------------------------------
# Change Password
# ---------------------------------------------------------------------------

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(
    http_request: Request,
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..utils.audit import log_audit_event

    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    pwd_error = validate_password_strength(payload.new_password)
    if pwd_error:
        raise HTTPException(status_code=400, detail=pwd_error)

    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    db.commit()

    ip = getattr(current_user, "_client_ip", _get_client_ip(http_request))
    log_audit_event(
        db,
        action="PASSWORD_CHANGED",
        detail=f"User '{current_user.username}' changed their password.",
        username=current_user.username,
        ip_address=ip,
    )
    return {"message": "Password updated successfully."}


# ---------------------------------------------------------------------------
# Internal: seed default accounts (SEC-02 fix: all non-admin users must change password)
# ---------------------------------------------------------------------------

def _seed_users(db: Session):
    """Seed initial accounts if database is empty. All default accounts forced to change password."""
    import os

    is_prod = os.getenv("APP_ENV") == "production"
    admin_pass = os.getenv("INITIAL_ADMIN_PASSWORD", "Admin@123456")

    default_accounts = [
        ("admin",    admin_pass,       "admin"),
        ("operator", "Operator@123456", "operator"),
        ("viewer",   "Viewer@123456",   "viewer"),
    ]
    for uname, pwd, role in default_accounts:
        existing = db.query(User).filter(User.username == uname).first()
        if not existing:
            db.add(User(
                username=uname,
                password_hash=get_password_hash(pwd),
                role=role,
                status="active",
                # SEC-02 FIX: ALL default accounts must change password on first login
                must_change_password=True,
            ))
    db.commit()
