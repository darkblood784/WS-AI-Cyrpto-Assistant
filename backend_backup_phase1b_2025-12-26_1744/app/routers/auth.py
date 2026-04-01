from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import User, Plan
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    generate_email_verification_token,
    hash_token,
)
from datetime import datetime, timezone
from app.core.password_policy import validate_password

router = APIRouter(prefix="/auth", tags=["auth"])

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MeResponse(BaseModel):
    id: str
    email: EmailStr
    is_active: bool

class VerifyEmailRequest(BaseModel):
    token: str

def normalize_email(email: str) -> str:
    return email.strip().lower()

@router.post("/register", response_model=MeResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = normalize_email(str(payload.email))

    try:
        validate_password(payload.password, email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")

    try:
        pw_hash = hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    raw_token, expires_at = generate_email_verification_token()
    token_hash = hash_token(raw_token)
    
    # Postgres column is "timestamp without time zone", so store UTC as naive
    expires_at_naive = expires_at.replace(tzinfo=None)
    free_plan_id = db.execute(select(Plan.id).where(Plan.code == "free")).scalar_one()

    user = User(
        email=email,
        password_hash=pw_hash,
        plan_id=free_plan_id,
        is_active=True,
        is_email_verified=False,
        email_verification_token=token_hash,
        email_verification_expires_at=expires_at_naive,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    print(f"[EMAIL_VERIFY] {user.email} token={raw_token} expires_at={expires_at.isoformat()}")
    return MeResponse(id=user.id, email=user.email, is_active=user.is_active)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = normalize_email(str(payload.email))

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")
    
    if not user.is_email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified.")

    token = create_access_token(sub=user.id)
    return TokenResponse(access_token=token)

@router.post("/verify")
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")

    token_hash = hash_token(token)
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    user = db.execute(
        select(User).where(User.email_verification_token == token_hash)
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")

    if user.is_email_verified:
        return {"ok": True, "already_verified": True}

    if not user.email_verification_expires_at or user.email_verification_expires_at < now_utc_naive:
        raise HTTPException(status_code=400, detail="Token expired")

    user.is_email_verified = True
    user.email_verification_token = None
    user.email_verification_expires_at = None
    db.commit()

    return {"ok": True}
    
def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token.")
    token = authorization.split(" ", 1)[1].strip()

    try:
        data = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    if data.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type.")

    user_id = data.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")
    return user

@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    return MeResponse(id=user.id, email=user.email, is_active=user.is_active)
