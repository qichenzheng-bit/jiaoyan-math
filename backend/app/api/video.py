"""Video production uses the original engine rather than reimplementing teaching decisions."""
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, audit, now
from app.models import TeachingResource, VideoProject, StudioItem, User
from app.api.resources import admin_lock
from app.api.studio import save_version
from app.services import video_engine as engine
from app.api import qoder
import threading
production_model_lock=threading.Lock()

def prepare_model(db,override=None):
    model=qoder.video_model_preference(db)
    if model not in {m['id'] for m in qoder.available_models()['models']}:
        raise HTTPException(422,'视频模型已不在可用清单，请重新配置')
    effort=override if override is not None else qoder.stored_effort(db,qoder.VIDEO_EFFORT_KEY)
    qoder.validate_effort(qoder.available_models(),model,effort,True)
    engine.configure_production_model(model,effort)

router = APIRouter(prefix="/video", dependencies=[Depends(current_user)])
write = [Depends(require_origin)]
class Start(BaseModel):
    resource_id: str = Field(max_length=36)
class InferenceOptions(BaseModel):
    effort: str|None = Field(default=None,max_length=16)
class Instruction(InferenceOptions):
    instruction: str = Field(min_length=1, max_length=12000)

def view(row):
    return {k: getattr(row, k) for k in ("id", "resource_id", "resource_revision", "source_snapshot", "engine_id", "work_id", "created_at")}

def row_for(db, ident):
    row = db.get(VideoProject, ident)
    if row is None:
        raise HTTPException(404, "视频项目不存在")
    return row

def remote(row):
    if not row.engine_id:
        raise HTTPException(409, "项目未成功绑定视频引擎")
    return engine.engine_id(row.engine_id)

def snapshot(r):
    result = { "title": r.title, "problem": r.content, "reference_solution": r.solution,
               "answer": r.answer, "subject": r.subject, "chapter": r.chapter,
               "exam_type": r.exam_type, "question_type": r.question_type,
               "analysis": r.analysis, "tags": r.tags or [], "fps": 60 }
    if not (result["reference_solution"] or "").strip():
        raise HTTPException(422, "请先在题库保存完整解析")
    # Old engine's schema has tighter bounds. Never silently truncate teaching material.
    for key, size in {"title":180,"problem":20000,"reference_solution":120000,"answer":4000,"subject":20,
                      "chapter":120,"exam_type":80,"question_type":20,"analysis":20000}.items():
        result[key] = result[key] or ""
        if len(result[key]) > size:
            raise HTTPException(422, f"题源字段 {key} 超过引擎限制")
    if any("![" in result[k] for k in ("problem", "reference_solution", "answer", "analysis")):
        raise HTTPException(422, "含附图题源需先完成跨引擎附件迁移，暂不可直接生成")
    return result

@router.get("/status")
def status():
    try:
        engine.call("GET", "/lessons/stats")
        return {"available": True, "source_revision": engine.SOURCE_REVISION, "detail": "引擎接口已连接；真实模型及渲染仍需验收"}
    except HTTPException as exc:
        return {"available": False, "source_revision": engine.SOURCE_REVISION, "detail": str(exc.detail)}

@router.get("/projects")
def listing(db: Session = Depends(get_db)):
    return [view(r) for r in db.scalars(select(VideoProject).order_by(VideoProject.created_at.desc()).limit(200))]

@router.post("/projects", dependencies=write)
def create(body: Start, db: Session = Depends(get_db), user: User = Depends(current_user)):
    engine.config()
    admin_lock(db, user)
    r = db.get(TeachingResource, body.resource_id)
    if not r or r.archived or r.kind != "question":
        raise HTTPException(404, "请选择有效题库题目")
    old = db.scalar(select(VideoProject).where(VideoProject.resource_id == r.id, VideoProject.resource_revision == r.revision))
    if old:
        return view(old)
    data = snapshot(r)
    # Save mapping before contacting the independent service; if response is lost, do not retry create blindly.
    row = VideoProject(id=str(uuid4()), resource_id=r.id, resource_revision=r.revision, source_snapshot=data, created_at=now())
    db.add(row)
    audit(db, "video.create", user.id)
    db.commit()
    try:
        result = engine.call("POST", "/lessons", data)
        row.engine_id = engine.engine_id(result.get("id") if isinstance(result,dict) else None)
        db.commit()
    except HTTPException:
        # Keep the pending local project for explicit reconciliation.
        raise
    return view(row)

@router.get("/projects/{ident}")
def detail(ident: str, db: Session = Depends(get_db)):
    row = row_for(db, ident)
    result = view(row)
    if row.engine_id:
        rid = remote(row)
        result["lesson"] = engine.call("GET", f"/lessons/{rid}")
        result["jobs"] = engine.call("GET", f"/jobs?lesson_id={rid}&limit=30")
    return result

@router.post("/projects/{ident}/{action}", dependencies=write)
def produce(ident: str, action: Literal["generate","render"], body: InferenceOptions|None=None, db: Session = Depends(get_db)):
    row = row_for(db, ident)
    if row.work_id:
        raise HTTPException(409, "审核归档的视频不可修改")
    rid=remote(row)
    if action=="generate":
        with production_model_lock:
            prepare_model(db,body.effort if body else None)
            return engine.call("POST", f"/lessons/{rid}/{action}", {})
    return engine.call("POST", f"/lessons/{rid}/{action}", {})

@router.post("/projects/{ident}/edit/submit", dependencies=write)
def edit(ident: str, body: Instruction, db: Session = Depends(get_db)):
    row = row_for(db, ident)
    if row.work_id:
        raise HTTPException(409, "审核归档的视频不可微调")
    rid=remote(row)
    with production_model_lock:
        prepare_model(db,body.effort)
        return engine.call("POST", f"/videos/{rid}/edits", {"instruction":body.instruction, "images":[]})

@router.get("/projects/{ident}/edits/history")
def history(ident: str, db: Session = Depends(get_db)):
    return engine.call("GET", f"/videos/{remote(row_for(db,ident))}/edits/history")

@router.get("/projects/{ident}/code")
def code(ident: str, db: Session = Depends(get_db)):
    return engine.call("GET", f"/lessons/{remote(row_for(db,ident))}/code")

@router.post("/projects/{ident}/jobs/{job_id}/{action}", dependencies=write)
def job_action(ident: str, job_id: str, action: Literal["cancel","retry"], db: Session = Depends(get_db)):
    row = row_for(db, ident)
    if row.work_id:
        raise HTTPException(409, "审核归档的视频不可修改")
    jid = engine.engine_id(job_id)
    job = engine.call("GET", f"/jobs/{jid}")
    if not isinstance(job,dict) or job.get("lesson_id") != remote(row):
        raise HTTPException(404, "任务不属于当前视频项目")
    return engine.call("POST", f"/jobs/{jid}/{action}", {})

@router.post("/projects/{ident}/review/approve", dependencies=write)
def approve(ident: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    admin_lock(db, user)
    row = row_for(db, ident)
    if row.work_id:
        return view(row)
    rid = remote(row)
    lesson = engine.call("GET", f"/lessons/{rid}")
    if lesson.get("video_review_status") != "approved":
        lesson = engine.call("POST", f"/videos/{rid}/review/approve", {})
    if lesson.get("video_review_status") != "approved" or not lesson.get("has_video"):
        raise HTTPException(409, "引擎尚未确认成片归档")
    # Keep media in engine's durable store. Studio records carry a local, authenticated link, not a disk path.
    data = {"category":"video","file_id":None,"document_id":None,"resource_id":row.resource_id,
            "content":"", "note":"视频引擎审核归档", "video_project_id":row.id}
    item = StudioItem(id=str(uuid4()), kind="work", title=row.source_snapshot["title"], data=data,
                      revision=1, archived=False, created_at=now(), updated_at=now())
    db.add(item); db.flush(); save_version(db,item); row.work_id=item.id
    audit(db,"video.approve",user.id); db.commit()
    return view(row)

@router.get("/projects/{ident}/media")
def media(ident: str, request: Request, download: bool=False, db: Session = Depends(get_db)):
    return engine.media(remote(row_for(db, ident)), download, request.headers.get("range"))
