import hashlib
import secrets
import time
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.models import User, LoginSession, AuditLog

COOKIE_NAME = "jiaoyan_session"
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

def now() -> int:
    return int(time.time())

def hash_password(password: str) -> str:
    return hasher.hash(password)

def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def require_origin(request: Request):
    if request.headers.get("origin") != settings.app_origin:
        raise HTTPException(403, "请求来源不受信任")

def audit(db: Session, action: str, user_id: int | None):
    db.add(AuditLog(action=action, user_id=user_id, created_at=now()))

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 128:
        raise HTTPException(401, "请先登录")
    session = db.get(LoginSession, token_hash(token))
    if session is None or session.expires_at <= now():
        raise HTTPException(401, "请先登录")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "请先登录")
    return user

def create_session(db: Session, response: Response, user_id: int):
    token = secrets.token_urlsafe(32)
    stamp = now()
    db.add(LoginSession(token_hash=token_hash(token), user_id=user_id,
        expires_at=stamp + settings.session_seconds, created_at=stamp))
    response.set_cookie(COOKIE_NAME, token, max_age=settings.session_seconds,
        httponly=True, secure=settings.secure_cookie, samesite="strict", path="/api")

def clear_cookie(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/api", httponly=True,
        secure=settings.secure_cookie, samesite="strict")
