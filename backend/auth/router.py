from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import User
from .helpers import verify_password, get_password_hash, create_access_token, verify_admin

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    username: str,
    password: str,
    role: str = "viewer",
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_admin)
):
    from ..utils.audit import log_audit_event
    if role not in ["admin", "operator", "viewer"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin', 'operator', or 'viewer'.")

    db_user = db.query(User).filter(User.username == username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    hashed_password = get_password_hash(password)
    new_user = User(username=username, password_hash=hashed_password, role=role, status="active")
    db.add(new_user)
    log_audit_event(db, action="USER_REGISTER", detail=f"User registered: {username} with role {role}", username=current_user.username)
    db.commit()
    db.refresh(new_user)
    return {
        "message": f"User registered successfully by {current_user.username}",
        "username": new_user.username,
        "role": new_user.role
    }


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    from ..utils.audit import log_audit_event
    # Auto-seed default test users on first login attempt if DB is empty
    _seed_users(db)

    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        log_audit_event(db, action="LOGIN_FAILED", detail=f"Failed login attempt for username '{form_data.username}'", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if getattr(user, "deleted_at", None) is not None or getattr(user, "status", "active") != "active":
        log_audit_event(db, action="LOGIN_BLOCKED", detail=f"Blocked login for disabled/suspended user '{user.username}'", username=user.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled or suspended. Contact an administrator."
        )

    access_token = create_access_token(data={"sub": user.username})
    log_audit_event(db, action="LOGIN_SUCCESS", detail=f"User '{user.username}' logged in successfully", username=user.username)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "must_change_password": getattr(user, "must_change_password", False)
    }


# ---------------------------------------------------------------------------
# Internal: seed default accounts
# ---------------------------------------------------------------------------

def _seed_users(db: Session):
    """Seed initial administrator account if database has no accounts."""
    import os
    admin_pass = os.getenv("INITIAL_ADMIN_PASSWORD", "Admin@123456")
    default_accounts = [
        ("admin", admin_pass, "admin"),
        ("operator", "Operator@123456", "operator"),
        ("viewer", "Viewer@123456", "viewer"),
    ]
    for uname, pwd, role in default_accounts:
        user = db.query(User).filter(User.username == uname).first()
        if not user:
            db.add(User(
                username=uname,
                password_hash=get_password_hash(pwd),
                role=role,
                status="active",
                must_change_password=True if uname == "admin" and os.getenv("APP_ENV") == "production" else False
            ))
    db.commit()
