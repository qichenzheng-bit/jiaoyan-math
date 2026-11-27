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


# F4.6: versioned, declarative, user-scoped layout profiles. No document contents,
# HTML, CSS or scripts may be supplied by the browser.
from typing import Literal
import hashlib
import json
from pydantic import ConfigDict, model_validator
from app.models import TeachingDocument, TeachingResource

class DocumentBlockStyle(BaseModel):
    model_config=ConfigDict(extra="forbid")
    size: float|None=Field(default=None,ge=6,le=36)
    lineHeight: float|None=Field(default=None,ge=1,le=3)
    paragraphGap: float|None=Field(default=None,ge=0,le=50)
    align: Literal["left","center","right","justify"]|None=None
    bold: bool|None=None
    frame: Literal["none","border","accent","fill"]|None=None
    role: Literal["normal","knowledge","definition","theorem","lemma","corollary","proof","example","exercise","method","warning","summary"]|None=None
    pageBreak: Literal["auto","before","after","alone"]|None=None
    answerSpace: float|None=Field(default=None,ge=0,le=180)
    headingLevel: Literal[1,2,3,4,5,6]|None=None
    optionColumns: Literal["auto",1,2,4]|None=None

class DocumentLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper: Literal["A4","A3","A5","B5","A6","custom"]="A4"
    width: float=Field(default=210,ge=50,le=1000)
    height: float=Field(default=297,ge=50,le=1000)
    landscape: bool=False
    top: float=Field(default=20,ge=0,le=100)
    bottom: float=Field(default=20,ge=0,le=100)
    left: float=Field(default=20,ge=0,le=100)
    right: float=Field(default=20,ge=0,le=100)
    columns: Literal[1,2,3]=1
    gap: float=Field(default=8,ge=3,le=30)
    font: Literal["serif","sans"]="serif"
    size: float=Field(default=10.5,ge=6,le=36)
    lineHeight: float=Field(default=1.5,ge=1,le=3)
    paragraphGap: float=Field(default=6,ge=0,le=50)
    keepQuestions: bool=True
    originalNumbers: bool=False
    answerSpace: float=Field(default=0,ge=0,le=180)
    header: str=Field(default="",max_length=200)
    footer: str=Field(default="第 {{当前页码}} 页，共 {{总页数}} 页",max_length=200)
    toc: bool=False
    tocDepth: Literal[1,2,3,4,5,6]=2
    chapterNewPage: bool=False
    mirrorMargins: bool=False
    titleSize: float=Field(default=18,ge=8,le=36)
    headingSize: float=Field(default=14,ge=8,le=36)
    subtitle: str=Field(default="",max_length=200)
    examTime: str=Field(default="",max_length=200)
    showScore: bool=True
    typeHeadings: bool=False
    numbering: Literal["continuous","section"]="continuous"
    optionColumns: Literal["auto",1,2,4]="auto"
    blankWidth: float=Field(default=0,ge=0,le=100)
    typeStyles: dict[str,DocumentBlockStyle]=Field(default_factory=dict,max_length=100)
    chapterStyles: dict[str,DocumentBlockStyle]=Field(default_factory=dict,max_length=5100)
    blockStyles: dict[str,DocumentBlockStyle]=Field(default_factory=dict,max_length=5100)

    @model_validator(mode="after")
    def printable_area(self):
        if any(not key or len(key)>100 or key in {"__proto__","constructor","prototype"} for rules in (self.typeStyles,self.chapterStyles,self.blockStyles) for key in rules):
            raise ValueError("样式编号无效")
        dims={"A4":(210,297),"A3":(297,420),"A5":(148,210),"B5":(176,250),"A6":(105,148)}
        w,h=sorted(dims.get(self.paper,(self.width,self.height)))
        if self.landscape:w,h=h,w
        if w-self.left-self.right-(self.columns-1)*self.gap<self.columns*20 or h-self.top-self.bottom<25:
            raise ValueError("页面有效排版空间不足")
        return self

class DocumentLayoutTemplate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    id: str=Field(min_length=1,max_length=80,pattern=r"^[A-Za-z0-9_-]+$")
    name: str=Field(min_length=1,max_length=80)
    kind: Literal["paper","handout","textbook","all"]
    layout: DocumentLayout
    isDefault: bool=False

class LayoutUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    revision: int=Field(ge=0)
    value: DocumentLayout

class TemplateUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    revision: int=Field(ge=0)
    value: list[DocumentLayoutTemplate]=Field(max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        ids=[t.id for t in self.value]
        if len(set(ids))!=len(ids) or set(ids)&{"paper","paper-double","handout","textbook","general"}:
            raise ValueError("模板编号重复或与系统模板冲突")
        default_kinds=[t.kind for t in self.value if t.isDefault]
        if len(set(default_kinds))!=len(default_kinds):
            raise ValueError("同类模板只能设置一个默认项")
        if any(t.layout.blockStyles or t.layout.chapterStyles for t in self.value):
            raise ValueError("模板不能携带特定文档的局部样式")
        if any(not t.name.strip() for t in self.value):
            raise ValueError("模板名称不能为空")
        return self

def _layout_key(user,scope,identity):
    return "layout:"+str(user.id)+":"+hashlib.sha256((scope+":"+identity).encode()).hexdigest()

def _layout_record(db,key,fallback=None):
    setting=db.get(Setting,key)
    return json.loads(setting.value) if setting else {"revision":0,"value":fallback,"history":[]}

def _layout_save(db,user,key,revision,value,fallback=None):
    # Serialize writes even for a profile not yet present in the settings table.
    db.scalar(select(User).where(User.id==user.id).with_for_update())
    old=_layout_record(db,key,fallback)
    if old["revision"]!=revision:
        raise HTTPException(409,"排版配置已被其他设备更新，请重新读取后保存")
    if old["value"]==value:return old
    history=([{"revision":old["revision"],"value":old["value"]}]+old["history"])[:2] if old["revision"] else []
    record={"revision":revision+1,"value":value,"history":history}
    db.merge(Setting(key=key,value=json.dumps(record,ensure_ascii=False)))
    audit(db,"document.layout.update",user.id)
    db.commit()
    return record

def _check_layout_target(db,scope,identity):
    model=TeachingDocument if scope=="doc" else TeachingResource
    target=db.get(model,identity)
    if not target or (scope=="source" and target.kind!="source"):
        raise HTTPException(404,"排版资料不存在")

@router.get("/document-layout/{scope}/{identity}")
def read_document_layout(scope:Literal["doc","source"],identity:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    _check_layout_target(db,scope,identity)
    return _layout_record(db,_layout_key(user,scope,identity))

@router.put("/document-layout/{scope}/{identity}",dependencies=[Depends(require_origin)])
def update_document_layout(scope:Literal["doc","source"],identity:str,body:LayoutUpdate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    _check_layout_target(db,scope,identity)
    return _layout_save(db,user,_layout_key(user,scope,identity),body.revision,body.value.model_dump(exclude_none=True))

@router.get("/document-templates")
def read_document_templates(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return _layout_record(db,_layout_key(user,"templates","all"),[])

@router.put("/document-templates",dependencies=[Depends(require_origin)])
def update_document_templates(body:TemplateUpdate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return _layout_save(db,user,_layout_key(user,"templates","all"),body.revision,[t.model_dump(exclude_none=True) for t in body.value],[])
