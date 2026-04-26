"""Password hashing + JWT helpers."""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

log = logging.getLogger("lotlegends.auth")


def _resolve_secret() -> str:
    """Pick a JWT signing secret.

    In production (LOTLEGENDS_ENV=production) the LOTLEGENDS_SECRET env var
    is required and must be at least 32 chars. In development we fall back
    to a stable dev secret with a warning so local restarts don't invalidate
    existing tokens.
    """
    env = os.getenv("LOTLEGENDS_ENV", "dev").lower()
    secret = os.getenv("LOTLEGENDS_SECRET", "").strip()
    if env == "production":
        if not secret or len(secret) < 32:
            raise RuntimeError(
                "LOTLEGENDS_SECRET must be set to at least 32 random characters "
                "when LOTLEGENDS_ENV=production"
            )
        return secret
    if not secret:
        log.warning(
            "LOTLEGENDS_SECRET not set — using dev fallback. "
            "Set this env var to a long random string before deploying."
        )
        return "dev-fallback-secret-change-me-in-prod-" + secrets.token_hex(8)
    return secret


SECRET_KEY = _resolve_secret()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 14


# ─── Password ──────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ─── JWT ───────────────────────────────────────────────────────────
def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[int]:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(data["sub"])
    except (JWTError, KeyError, ValueError):
        return None


# ─── FastAPI dependency ────────────────────────────────────────────
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = auth.split(" ", 1)[1].strip()
    user_id = decode_token(token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ต้องเป็นผู้ดูแลระบบเท่านั้น")
    return user
