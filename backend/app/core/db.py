from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from fastapi import HTTPException
from app.core.config import settings

class Base(DeclarativeBase):
    pass

@lru_cache
def engine():
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    return create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)

def get_db():
    if not settings.database_url:
        raise HTTPException(503, "数据库尚未配置")
    with Session(engine(), expire_on_commit=False) as db:
        yield db

def session_factory():
    return sessionmaker(engine(), expire_on_commit=False)
