from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import (COOKIE_NAME, audit, clear_cookie, create_session,
    current_user, hash_password, now, require_origin, token_hash, verify_password, hasher)
from app.models import User, LoginSession

router = APIRouter(prefix="/auth", tags=["auth"])
MAX_FAILURES = 5
LOCK_SECONDS = 300

class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)

class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

def locked_admin(db: Session) -> User:
    # Single administrator; row lock serializes login attempts across workers.
    user = db.scalar(select(User).where(User.id == 1).with_for_update().execution_options(populate_existing=True))
    if not user:
        raise HTTPException(503, "管理员尚未初始化")
    return user

def check_lock(user: User):
    if user.locked_until > now():
        raise HTTPException(429, "尝试次数过多，请稍后重试")
    if user.locked_until:
        user.locked_until = 0
        user.failed_attempts = 0

def fail(db: Session, user: User):
    user.failed_attempts += 1
    if user.failed_attempts >= MAX_FAILURES:
        user.locked_until = now() + LOCK_SECONDS
    audit(db, "auth.failure", user.id)
    db.commit()
    raise HTTPException(401, "用户名或密码错误")

@router.post("/login", dependencies=[Depends(require_origin)])
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    user = locked_admin(db)
    check_lock(user)
    valid = verify_password(user.password_hash, body.password)
    if not valid or body.username != user.username:
        fail(db, user)
    user.failed_attempts = 0
    user.locked_until = 0
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now()))
    old_token = request.cookies.get(COOKIE_NAME)
    if old_token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(old_token)))
    create_session(db, response, user.id)
    audit(db, "auth.login", user.id)
    db.commit()
    return {"username": user.username}

@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username}

@router.post("/logout", dependencies=[Depends(require_origin)])
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(request.cookies[COOKIE_NAME])))
    audit(db, "auth.logout", user.id)
    db.commit()
    clear_cookie(response)
    return {"ok": True}

@router.post("/password", dependencies=[Depends(require_origin)])
def change_password(body: PasswordChange, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    user = locked_admin(db)
    check_lock(user)
    if not verify_password(user.password_hash, body.current_password):
        fail(db, user)
    user.password_hash = hash_password(body.new_password)
    user.failed_attempts = 0
    user.locked_until = 0
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    create_session(db, response, user.id)
    audit(db, "auth.password_change", user.id)
    db.commit()
    return {"ok": True}
