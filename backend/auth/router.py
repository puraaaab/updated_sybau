from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import User
from .helpers import verify_password, get_password_hash, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    username: str,
    password: str,
    role: str = "viewer",
    db: Session = Depends(get_db)
):
    if role not in ["admin", "operator", "viewer"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin', 'operator', or 'viewer'.")

    db_user = db.query(User).filter(User.username == username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    hashed_password = get_password_hash(password)
    new_user = User(username=username, password_hash=hashed_password, role=role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "message": "User registered successfully",
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
    # Auto-seed default test users on first login attempt if DB is empty
    _seed_users(db)

    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username
    }


# ---------------------------------------------------------------------------
# Internal: seed default accounts
# ---------------------------------------------------------------------------

def _seed_users(db: Session):
    """Seed default production user accounts if missing."""
    default_accounts = [
        ("admin", "Admin@123456", "admin"),
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
            ))
    db.commit()
