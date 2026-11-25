import os
import shutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.core.security import audit, current_user, require_origin
from app.models import Setting, AuditLog, User
from app.services.storage import root

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(current_user)])

class Preferences(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    theme: str = Field(pattern="^(light|dark|system)$")

@router.get("")
def preferences(db: Session = Depends(get_db)):
    values = {s.key:s.value for s in db.scalars(select(Setting).where(Setting.key.in_(["display_name","theme"])))}
    return {"display_name":values.get("display_name","微光数学"),"theme":values.get("theme","light")}

@router.put("", dependencies=[Depends(require_origin)])
def update(body: Preferences, db: Session = Depends(get_db), user: User = Depends(current_user)):
    name = body.display_name.strip()
    if not name:
        raise HTTPException(422,"名称不能为空")
    values = {"display_name":name,"theme":body.theme}
    for key,value in values.items():
        db.merge(Setting(key=key,value=value))
    audit(db,"settings.update",user.id)
    db.commit()
    return values

@router.get("/status")
def status():
    disk = None
    if settings.storage_root:
        usage = shutil.disk_usage(root())
        disk = {"total":usage.total,"free":usage.free}
    return {"version":settings.version,"release":os.environ.get("RELEASE_SHA","development"),"disk":disk}

@router.get("/audit")
def logs(db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc(),AuditLog.id.desc()).limit(100))
    return [{"id":row.id,"action":row.action,"created_at":row.created_at} for row in rows]
