from datetime import datetime, timedelta, timezone
import secrets
import hashlib

from jose import jwt
from app.core.config import settings
from passlib.hash import argon2


EMAIL_VERIFY_TOKEN_BYTES = 32
EMAIL_VERIFY_TOKEN_TTL_HOURS = 24


def generate_email_verification_token() -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(EMAIL_VERIFY_TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=EMAIL_VERIFY_TOKEN_TTL_HOURS)
    return raw, expires_at


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return argon2.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return argon2.verify(password, password_hash)


def create_access_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.JWT_ACCESS_MINUTES)
    return jwt.encode({"sub": sub, "type": "access", "exp": exp}, settings.JWT_SECRET, algorithm="HS256")


def create_refresh_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=settings.JWT_REFRESH_DAYS)
    return jwt.encode({"sub": sub, "type": "refresh", "exp": exp}, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
