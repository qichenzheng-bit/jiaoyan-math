from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.core.security import current_user

router = APIRouter(tags=["system"])

@router.get("/health")
def health():
    return {"status": "ok", "version": settings.version}

@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    db.execute(text("SELECT id FROM users WHERE id = 1"))
    return {"status": "ok"}

@router.get("/system", dependencies=[Depends(current_user)])
def system():
    return {"name": settings.app_name, "version": settings.version}
