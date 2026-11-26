import os
from pathlib import Path
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
    release_file = Path(__file__).resolve().parents[3] / "RELEASE_SHA"
    release = release_file.read_text().strip() if release_file.is_file() else "development"
    return {"version":settings.version,"release":release,"disk":disk}

@router.get("/audit")
def logs(db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc(),AuditLog.id.desc()).limit(100))
    return [{"id":row.id,"action":row.action,"created_at":row.created_at} for row in rows]

# Keep the backup credentials and arbitrary error details out of the web API.
def backup_state():
    import json
    import re
    import subprocess
    base = Path.home() / "jiaoyan-app"
    state_dir = base / "backup-state"
    configured = (base / "config" / "backup.json").is_file()
    def read(name):
        try:
            raw = json.loads((state_dir / name).read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            allowed = {}
            if raw.get("state") in ("running", "success", "unchanged", "failed"):
                allowed["state"] = raw["state"]
            if isinstance(raw.get("at"), str) and re.fullmatch(r"[0-9TZ:+.\-]{10,40}", raw["at"]):
                allowed["at"] = raw["at"]
            if isinstance(raw.get("commit"), str) and re.fullmatch(r"[0-9a-f]{40}", raw["commit"]):
                allowed["commit"] = raw["commit"]
            if type(raw.get("entries")) is int and raw["entries"] >= 0:
                allowed["entries"] = raw["entries"]
            if raw.get("state") == "failed":
                allowed["error"] = "备份失败，请查看服务器服务状态"
            return allowed
        except (OSError, ValueError):
            return None
    timer = False
    running = False
    if configured:
        try:
            timer = subprocess.run(["systemctl", "--user", "is-active", "--quiet", "jiaoyan-backup.timer"],
                timeout=3, capture_output=True).returncode == 0
            # A oneshot service is activating while it is running.
            result = subprocess.run(["systemctl", "--user", "show", "-p", "ActiveState", "--value", "jiaoyan-backup.service"],
                timeout=3, capture_output=True, text=True)
            running = result.stdout.strip() in ("activating", "active", "reloading")
        except (OSError, subprocess.SubprocessError):
            pass
    latest = read("status.json")
    if latest and latest.get("state") == "running" and not running:
        latest = {**latest, "state": "failed", "error": "备份进程已停止，请检查服务器"}
    return {"configured": configured, "timer_active": timer, "running": running,
            "schedule": "每天北京时间 24:00", "latest": latest, "last_success": read("last-success.json")}

@router.get("/backup")
def backup_status():
    return backup_state()

@router.post("/backup/run", dependencies=[Depends(require_origin)])
def backup_run(db: Session = Depends(get_db), user: User = Depends(current_user)):
    import subprocess
    state = backup_state()
    if not state["configured"] or not state["timer_active"]:
        raise HTTPException(409, "请先由管理员完成备份配置与首次上传验证")
    if state["running"]:
        raise HTTPException(409, "备份正在执行")
    try:
        result = subprocess.run(["systemctl", "--user", "start", "--no-block", "jiaoyan-backup.service"],
                                timeout=5, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        raise HTTPException(503, "无法提交备份任务") from None
    if result.returncode != 0:
        raise HTTPException(503, "无法提交备份任务")
    audit(db, "backup.request", user.id)
    db.commit()
    return {"accepted": True}
