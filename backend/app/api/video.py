"""Video production uses the original engine rather than reimplementing teaching decisions."""
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.method_recommendation import video_solution
from app.core.security import current_user, require_origin, audit, now
from app.models import TeachingResource, VideoProject, StudioItem, User, StoredFile
from app.api.resources import admin_lock, view as resource_view
from app.services import work_facets
from app.api.studio import save_version
from app.services import video_engine as engine, storage
from app.api import qoder
import threading
production_model_lock=threading.Lock()

def prepare_model(db,override=None,model_override=None):
    model=model_override or qoder.video_model_preference(db)
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
    model: str|None = Field(default=None,max_length=80)
    effort: str|None = Field(default=None,max_length=16)
class Instruction(InferenceOptions):
    instruction: str = Field(min_length=1, max_length=12000)

class CoverSelection(BaseModel):
    file_id: str = Field(max_length=36)
    timestamp: float = Field(ge=0,le=86400)
    revision: int = Field(ge=0)

def view(row,db=None):
    result={k: getattr(row, k) for k in ("id", "resource_id", "resource_revision", "source_snapshot", "engine_id", "work_id", "created_at")}
    if db is not None and row.work_id:
        item=db.get(StudioItem,row.work_id)
        if item:result.update(cover_file_id=item.data.get("cover_file_id"),cover_timestamp=item.data.get("cover_timestamp"))
    return result

def save_cover(db,row,item,body):
    image=db.get(StoredFile,body.file_id)
    if not image or image.archived or image.media_type!="image/png":
        raise HTTPException(422,"请选择有效的视频截帧")
    storage.link_file(db,body.file_id,"studio_item",item.id)
    item.data={**item.data,"cover_file_id":body.file_id,"cover_timestamp":body.timestamp,"cover_revision":body.revision}


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
    if hasattr(r,'bank_facts') and (not (r.bank_facts or {}).get('answer_complete') or not (r.bank_facts or {}).get('solution_complete')):
        raise HTTPException(422,'请先补齐答案和全部小问解析')
    try:solution=video_solution(r)
    except ValueError as e:raise HTTPException(422,str(e))
    result = { "title": r.title, "problem": r.content, "reference_solution": solution,
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
    if any("![" in result[k] or "[[img:" in result[k] for k in ("problem", "reference_solution", "answer", "analysis")):
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
    return [view(r,db) for r in db.scalars(select(VideoProject).order_by(VideoProject.created_at.desc()).limit(200))]

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
    facets = work_facets.capture(db, {"subject":r.subject,"blocks":[{"resource_id":r.id,"snapshot":resource_view(r)}]})
    row = VideoProject(id=str(uuid4()), resource_id=r.id, resource_revision=r.revision, source_snapshot=data, work_facets=facets, created_at=now())
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
    result = view(row,db)
    if row.engine_id:
        rid = remote(row)
        result["lesson"] = engine.call("GET", f"/lessons/{rid}")
        result["jobs"] = engine.call("GET", f"/jobs?lesson_id={rid}&limit=30")
    return result

@router.post("/projects/{ident}/{action}", dependencies=write)
def produce(ident: str, action: Literal["generate","render"], body: InferenceOptions|None=None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = row_for(db, ident)
    if row.work_id:
        raise HTTPException(409, "审核归档的视频不可修改")
    rid=remote(row)
    if action=="generate":
        with production_model_lock:
            prepare_model(db,body.effort if body else None,body.model if body else None)
            from app.core.ai_preferences import video_supplement
            supplement=video_supplement(db,user) if isinstance(user,User) else {"text":"","revision":0}
            if supplement["text"]:
                return engine.call("POST",f"/jiaoyan/lessons/{rid}/generate",supplement)
            return engine.call("POST", f"/lessons/{rid}/{action}", {})
    return engine.call("POST", f"/lessons/{rid}/{action}", {})

@router.post("/projects/{ident}/edit/submit", dependencies=write)
def edit(ident: str, body: Instruction, db: Session = Depends(get_db), user:User=Depends(current_user)):
    row = row_for(db, ident)
    if row.work_id:
        raise HTTPException(409, "审核归档的视频不可微调")
    rid=remote(row)
    from app.core.ai_preferences import video_supplement
    extra=video_supplement(db,user)["text"] if isinstance(user,User) else ""
    instruction=body.instruction+("\n\n【教学补充要求；当前微调指令优先】\n"+extra if extra else "")
    if len(instruction)>12000:raise HTTPException(422,"微调要求及教学补充内容过长")
    with production_model_lock:
        prepare_model(db,body.effort,body.model)
        return engine.call("POST", f"/videos/{rid}/edits", {"instruction":instruction+"\n\n固定约束：不得修改视频分辨率、帧率、基础渲染配置、语音音色或语速；仅修改指令涉及的教学内容。", "images":[]})

@router.get("/projects/{ident}/edits/history")
def history(ident: str, db: Session = Depends(get_db)):
    return engine.call("GET", f"/videos/{remote(row_for(db,ident))}/edits/history")

def followup_render(ident:str,generation:dict,db):
    """Generation succeeds before its automatically enqueued render completes."""
    rid=remote(row_for(db,ident))
    started=generation.get("created_at")
    revision=generation.get("expected_revision")
    if not isinstance(started,str) or revision is None:
        raise HTTPException(502,"引擎未返回生成任务的版本或时间")
    jobs=engine.call("GET",f"/jobs?lesson_id={rid}&limit=200")
    if not isinstance(jobs,list):raise HTTPException(502,"引擎任务列表无效")
    candidates=[j for j in jobs if isinstance(j,dict) and j.get("lesson_id")==rid and j.get("kind")=="render"
        and j.get("expected_revision")==revision and isinstance(j.get("created_at"),str) and j["created_at"]>=started]
    if not candidates:raise HTTPException(502,"生成已结束但未找到对应渲染任务")
    first=min(candidates,key=lambda j:(j["created_at"],j.get("id","")))
    return job_read(ident,first.get("id"),db)

def job_read(ident:str,job_id:str,db:Session=Depends(get_db)):
    row=row_for(db,ident)
    job=engine.call("GET",f"/jobs/{engine.engine_id(job_id)}")
    if not isinstance(job,dict) or job.get("lesson_id")!=remote(row):
        raise HTTPException(404,"任务不属于当前视频项目")
    return {k:job.get(k) for k in ("id","lesson_id","kind","status","phase","overall","error","expected_revision","created_at")}

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
def approve(ident: str, body: CoverSelection|None=None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    admin_lock(db, user)
    row = row_for(db, ident)
    if row.work_id and body is None:return view(row,db)
    rid = remote(row)
    lesson = engine.call("GET", f"/lessons/{rid}")
    if body:
        if not lesson.get("has_video") or lesson.get("revision")!=body.revision:raise HTTPException(409,"成片版本已变化，请重新截取")
        image=db.get(StoredFile,body.file_id)
        if not image or image.archived or image.media_type!="image/png":raise HTTPException(422,"封面无效")
        jobs=engine.call("GET",f"/jobs?lesson_id={rid}&limit=30")
        if any(j.get("status") in ("running","queued","cancelling") for j in jobs):raise HTTPException(409,"视频任务仍在执行")
    if row.work_id:
        if body:
            item=db.get(StudioItem,row.work_id)
            if not item:raise HTTPException(409,"作品记录不存在")
            save_cover(db,row,item,body);item.revision+=1;item.updated_at=now();save_version(db,item);db.commit()
        return view(row,db)
    if lesson.get("video_review_status") != "approved":
        lesson = engine.call("POST", f"/videos/{rid}/review/approve", {})
    if lesson.get("video_review_status") != "approved" or not lesson.get("has_video"):
        raise HTTPException(409, "引擎尚未确认成片归档")
    # Keep media in engine's durable store. Studio records carry a local, authenticated link, not a disk path.
    data = {"category":"video","file_id":None,"document_id":None,"resource_id":row.resource_id,
            "content":"", "note":"视频引擎审核归档", "video_project_id":row.id}
    item = StudioItem(id=str(uuid4()), kind="work", title=row.source_snapshot["title"], data=data,
                      revision=1, archived=False, created_at=now(), updated_at=now())
    db.add(item); db.flush()
    if body:save_cover(db,row,item,body)
    save_version(db,item); row.work_id=item.id
    audit(db,"video.approve",user.id); db.commit()
    return view(row,db)

@router.get("/projects/{ident}/media")
def media(ident: str, request: Request, download: bool=False, db: Session = Depends(get_db)):
    return engine.media(remote(row_for(db, ident)), download, request.headers.get("range"))
