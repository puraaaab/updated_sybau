import os
import datetime
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
import bcrypt as _bcrypt_lib
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import User

# ---------------------------------------------------------------------------
# Security Configuration
# ---------------------------------------------------------------------------

# Secret key loaded from environment — NEVER hardcode in production.
# Set VMS_SECRET_KEY environment variable before deploying.
SECRET_KEY = os.getenv("VMS_SECRET_KEY", "vms_dev_secret_key_CHANGE_ME_IN_PRODUCTION")
if os.getenv("APP_ENV") == "production" and SECRET_KEY == "vms_dev_secret_key_CHANGE_ME_IN_PRODUCTION":
    raise RuntimeError("FATAL: VMS_SECRET_KEY must be set in production mode!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# NOTE: Using bcrypt directly because passlib 1.7.4 is incompatible with bcrypt 4.x / 5.x.

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


# ---------------------------------------------------------------------------
# Password Helpers (bcrypt)
# ---------------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored hash.
    Supports both bcrypt hashes and legacy SHA-256 hashes (for smooth migration).
    """
    # Detect bcrypt hashes (they start with $2b$ or $2a$)
    if hashed_password.startswith(("$2b$", "$2a$", "$2y$")):
        return _bcrypt_lib.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    # Legacy SHA-256 fallback (for existing seeded users until they next log in)
    import hashlib
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == hashed_password


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt (bcrypt 4.x / 5.x compatible)."""
    salt = _bcrypt_lib.gensalt()
    return _bcrypt_lib.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# ---------------------------------------------------------------------------
# JWT Token Helpers
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta if expires_delta else datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    if getattr(user, "status", "active") != "active" or getattr(user, "deleted_at", None) is not None:
        raise credentials_exception
    return user


# ---------------------------------------------------------------------------
# Role-Based Access Control (RBAC)
# ---------------------------------------------------------------------------

class RoleChecker:
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Operation not permitted. "
                    f"Required roles: {self.allowed_roles}. "
                    f"Current role: {current_user.role}"
                )
            )
        return current_user


# Predefined role dependency shortcuts
verify_admin = RoleChecker(["admin"])
verify_operator = RoleChecker(["admin", "operator"])
verify_viewer = RoleChecker(["admin", "operator", "viewer"])


def verify_camera_access(camera_id: str, user: User) -> bool:
    """
    Checks if a user has permission to view or manage a specific camera.
    Admins have unrestricted access. Operators/viewers are checked against allowed_cameras JSON list.
    """
    if not user:
        return False
    if user.role == "admin":
        return True
    
    import json
    allowed_list = []
    if getattr(user, "allowed_cameras", None):
        try:
            allowed_list = json.loads(user.allowed_cameras)
        except (ValueError, TypeError):
            allowed_list = []
            
    # If no specific cameras are set in allowed_cameras, default to granting access
    if not allowed_list:
        return True
        
    return camera_id in allowed_list

