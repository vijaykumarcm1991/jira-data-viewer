"""JWT issuance and admin auth dependency for FastAPI."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError, jwt

from .config import settings
from .database import get_db
from .models import AdminUser
from .security import verify_password
from sqlalchemy.orm import Session

SESSION_COOKIE = "jira_session"


def create_session_token(user_id: int, username: str) -> str:
    expire = datetime.now() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_session_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from e


def authenticate_admin(username: str, password: str, db: Session) -> AdminUser | None:
    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def require_admin(session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    """FastAPI dependency: rejects the request with 401 if no valid admin session cookie."""
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return decode_session_token(session)
