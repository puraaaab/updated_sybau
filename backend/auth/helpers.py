import os
import datetime
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt
import bcrypt as _bcrypt_lib
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import User

# ---------------------------------------------------------------------------
# Security Configuration
# ---------------------------------------------------------------------------

import secrets
import logging

logger = logging.getLogger(__name__)

_raw_secret = os.getenv("VMS_SECRET_KEY")
if not _raw_secret:
    if os.getenv("APP_ENV") == "production":
        raise RuntimeError("FATAL: VMS_SECRET_KEY environment variable MUST be explicitly set in production mode!")
    SECRET_KEY = secrets.token_urlsafe(32)
    logger.warning("SECURITY WARNING: VMS_SECRET_KEY is not set. Generated ephemeral 256-bit random key for this session.")
else:
    SECRET_KEY = _raw_secret
    if os.getenv("APP_ENV") == "production" and SECRET_KEY in (
        "vms_dev_secret_key_CHANGE_ME_IN_PRODUCTION",
        "dev_secret_key_sybau_vms_2026",
    ):
        raise RuntimeError("FATAL: VMS_SECRET_KEY is set to a known weak default string in production mode!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)


# ---------------------------------------------------------------------------
# Password Helpers (bcrypt)
# ---------------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith(("$2b$", "$2a$", "$2y$")):
        return _bcrypt_lib.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    import hashlib
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == hashed_password


def get_password_hash(password: str) -> str:
    salt = _bcrypt_lib.gensalt(rounds=12)
    return _bcrypt_lib.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def validate_password_strength(password: str) -> Optional[str]:
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    return None


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    from ..utils.timezone import get_ist_now
    if expires_delta:
        expire = get_ist_now() + expires_delta
    else:
        expire = get_ist_now() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _extract_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def get_current_user(
    request: Request,
    token_header: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = token_header
    if not token:
        token = request.query_params.get("token")

    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    if getattr(user, "status", "active") != "active" or getattr(user, "deleted_at", None) is not None:
        raise credentials_exception

    # BUG-04 FIX: Enforce must_change_password server-side.
    # If the user has not yet changed their default password, block ALL endpoints
    # except the change-password and login endpoints themselves.
    if getattr(user, "must_change_password", False):
        path = request.url.path
        exempt_paths = ("/api/v1/auth/change-password", "/api/v1/auth/login")
        if not any(path.endswith(ep) or path.startswith(ep) for ep in exempt_paths):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must change your default password before accessing this resource. "
                       "POST to /api/v1/auth/change-password with your current and new password.",
            )

    user._client_ip = _extract_client_ip(request)
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


verify_admin = RoleChecker(["admin"])
verify_operator = RoleChecker(["admin", "operator"])
verify_viewer = RoleChecker(["admin", "operator", "viewer"])


def verify_media_access(
    request: Request,
    token_header: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    token = token_header or request.query_params.get("token")
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username:
            user = db.query(User).filter(User.username == username).first()
            if user:
                return user
    except Exception:
        pass

    return None


def verify_camera_access(camera_id: str, user: User) -> bool:
    """Returns True if `user` is allowed to access `camera_id`.

    Semantics:
      - Admins always have full access.
      - Non-admin users: if `allowed_cameras` is an EMPTY list (the default),
        they can access ALL cameras (unrestricted mode).
      - If `allowed_cameras` contains a non-empty list of camera IDs, the user
        is restricted to ONLY those cameras (whitelist mode).
    """
    if not user:
        return False
    if user.role == "admin":
        return True

    import json
    allowed_list = []
    raw = getattr(user, "allowed_cameras", None)
    if raw:
        try:
            allowed_list = json.loads(raw)
        except (ValueError, TypeError):
            allowed_list = []

    # Empty list → unrestricted (admin hasn't set a camera whitelist for this user)
    if not allowed_list:
        return True

    # Non-empty list → only the listed cameras are accessible
    return camera_id in allowed_list
