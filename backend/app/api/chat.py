"""Private chat history; Qoder worker gets only bounded user-provided text."""
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, now, audit
from app.models import ChatSession, ChatMessage, StoredFile, FileReference, Setting, User
from app.services import storage
from app.api import qoder
from app.core import resource_context

router=APIRouter(prefix="/chat",tags=["chat"],dependencies=[Depends(current_user)])
TERMINAL={"done","failed","stopped"}
INTAKE_INTENTS={"question","knowledge","document","mixed"}
def public(s):
    return {k:getattr(s,k) for k in ("id","title","project","pinned","archived","created_at","updated_at")}
def message(m):
    return {k:getattr(m,k) for k in ("id","role","content","state","detail","model","attachments","resource_refs","created_at","intake_intent")}
def session(db,ident,locked=False):
    query=select(ChatSession).where(ChatSession.id==ident)
    s=db.scalar(query.with_for_update() if locked else query)
    if s is None: raise HTTPException(404,"会话不存在")
    return s
def messages(db,s):
    return list(db.scalars(select(ChatMessage).where(ChatMessage.session_id==s.id).order_by(ChatMessage.position)))
def sync(db,m):
    if m.state!="running": return
    from app.core import ai_chat
    state=ai_chat.load(db,m)
    if state is not None:
        ai_chat.sync(db,m,state);return
    ai_chat.retire_old(db,m)
def detail(db,s):
    from app.core import ai_chat
    rows=messages(db,s)
    for m in rows: sync(db,m)
    db.commit()
    return {**public(s),"messages":[{**message(m),"tool_trace":ai_chat.trace(db,m) if m.role=="assistant" else []} for m in rows]}

class NewSession(BaseModel):
    title:str=Field(default="新聊天",min_length=1,max_length=160)
    project:str=Field(default="",max_length=100)
class Patch(BaseModel):
    title:str|None=Field(default=None,min_length=1,max_length=160)
    project:str|None=Field(default=None,max_length=100)
    pinned:bool|None=None
class Turn(BaseModel):
    content:str=Field(min_length=1,max_length=12000)
    model:str=Field(default="Auto",max_length=80,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
    effort:str|None=Field(default=None,max_length=16)
    attachments:list[str]=Field(default_factory=list,max_length=4)
    resource_ids:list[str]=Field(default_factory=list,max_length=10)
    retrieval_query:str=Field(default="",max_length=200)
    rewind_id:str|None=Field(default=None,max_length=36)
@router.get("/sessions")
def listing(q:str=Query("",max_length=160),db:Session=Depends(get_db)):
    stmt=select(ChatSession)
    if q.strip(): stmt=stmt.where(ChatSession.title.contains(q.strip(),autoescape=True)|ChatSession.project.contains(q.strip(),autoescape=True))
    return [public(s) for s in db.scalars(stmt.order_by(ChatSession.pinned.desc(),ChatSession.updated_at.desc(),ChatSession.id).limit(100))]
@router.post("/sessions",dependencies=[Depends(require_origin)])
def create(body:NewSession,db:Session=Depends(get_db)):
    s=ChatSession(id=str(uuid4()),title=body.title.strip() or "新聊天",project=body.project.strip(),pinned=False,archived=False,created_at=now(),updated_at=now())
    db.add(s);db.commit()
    return public(s)
@router.get("/sessions/{ident}")
def read(ident:str,db:Session=Depends(get_db)):
    return detail(db,session(db,ident,True))
@router.patch("/sessions/{ident}",dependencies=[Depends(require_origin)])
def patch(ident:str,body:Patch,db:Session=Depends(get_db)):
    s=session(db,ident,True)
    for key,val in body.model_dump(exclude_none=True).items():
        setattr(s,key,val.strip() if isinstance(val,str) else val)
    if not s.title: raise HTTPException(422,"标题不能为空")
    s.updated_at=now();db.commit()
    return public(s)

@router.delete("/sessions/{ident}",dependencies=[Depends(require_origin)])
def remove_session(ident:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=session(db,ident,True)
    rows=messages(db,s)
    for m in rows:
        sync(db,m)
    if any(m.state=="running" for m in rows):
        db.commit()
        raise HTTPException(409,"请先停止生成，再删除会话")
    ids=[m.id for m in rows]
    if ids:
        from app.core import ai_chat
        native=[state for m in rows if m.role=="assistant" and (state:=ai_chat.load(db,m)) and state.get("native")]
        if native:
            if any(state.get("native_actor")!=user.id for state in native):raise HTTPException(403,"无权清理该原生会话")
            result=qoder.request("POST","/agent/delete-workspace",{"workspace":s.id,"owner":user.id})
            if not result.get("deleted"):raise HTTPException(503,"原生会话尚未清理，保留应用历史")
        db.execute(delete(FileReference).where(FileReference.owner_type=="chat_message",FileReference.owner_id.in_(ids)))
        db.execute(delete(Setting).where(Setting.key.in_([ai_chat.key(mid) for mid in ids])))
        db.execute(delete(ChatMessage).where(ChatMessage.session_id==s.id))
    db.delete(s)
    audit(db,"chat.delete",user.id)
    db.commit()
    return {"deleted":True,"id":ident}

def attachments(db,ids):
    result=[]
    for ident in dict.fromkeys(ids):
        f=db.get(StoredFile,ident)
        if f is None or f.archived: raise HTTPException(404,"附件不存在")
        from app.services import material_import as imp
        if f.media_type in {"text/plain","text/csv"} and f.size_bytes<=64000:
            try: content=storage.file_path(f).read_text(encoding="utf-8-sig")
            except (OSError,UnicodeError): raise HTTPException(422,"无法读取附件")
            if len(content)>16000: raise HTTPException(422,"附件正文超过16000字，请拆分")
        elif f.media_type in {"application/pdf",imp.DOCX,*storage.IMAGE_TYPES,*imp.TEXT}:
            content="本附件尚未读取。需要内容时调用原件读取工具；图片、PDF及Word内嵌图片采用AI视觉理解。未核对的识别结果须标明。"
        else:raise HTTPException(415,"不支持的附件类型")
        result.append((f,content))
    return result

@router.post("/sessions/{ident}/turn",dependencies=[Depends(require_origin)])
def turn(ident:str,body:Turn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=session(db,ident,True)
    rows=messages(db,s)
    for m in rows: sync(db,m)
    if any(m.state=="running" for m in rows):
        db.commit()
        raise HTTPException(409,"当前会话正在生成")
    if not body.content.strip(): raise HTTPException(422,"请输入内容")
    status=qoder.request("GET","/status")
    if not status.get("chat_available"): raise HTTPException(503,"独立 Qoder 执行服务需要升级至 M03")
    effort_args=qoder.assistant_effort(db,body.model,body.effort)
    attached=attachments(db,body.attachments)
    refs,context=resource_context.prepare(db,body.resource_ids,body.retrieval_query)
    if body.rewind_id:
        target=next((m for m in rows if m.id==body.rewind_id and m.role=="user"),None)
        if not target: raise HTTPException(404,"原消息不存在")
        # Preserve existing history by branching rather than overwriting.
        old=s
        s=ChatSession(id=str(uuid4()),title=(old.title+"（分支）")[:160],project=old.project,pinned=False,archived=False,created_at=now(),updated_at=now())
        db.add(s);db.flush()
        copied=[]
        for m in rows:
            if m.position>=target.position: break
            copy=ChatMessage(id=str(uuid4()),session_id=s.id,position=m.position,role=m.role,content=m.content,state=m.state,detail=m.detail,model=m.model,attachments=m.attachments,resource_refs=m.resource_refs,created_at=m.created_at,intake_intent=m.intake_intent)
            db.add(copy);db.flush()
            for f in m.attachments: storage.link_file(db,f["id"],"chat_message",copy.id)
            copied.append(copy)
        rows=copied
    from app.core import native_chat
    if not status.get("native_agent"):raise HTTPException(503,"请升级Qoder Worker并验证原生SDK")
    return native_chat.begin_turn(db,s,rows,body,user,attached,refs,context,effort_args)
@router.post("/sessions/{ident}/stop",dependencies=[Depends(require_origin)])
def stop(ident:str,db:Session=Depends(get_db)):
    s=session(db,ident,True)
    for m in messages(db,s):
        if m.state=="running":
            from app.core import ai_chat
            job=ai_chat.stop_job(db,m)
            if not job:continue
            try: qoder.request("POST","/chat/"+job+"/cancel",{})
            except HTTPException as exc:
                if exc.status_code!=404: raise
            sync(db,m)
    db.commit()
    return detail(db,s)

@router.get("/resource-search")
def resource_search(q:str=Query("",max_length=200),db:Session=Depends(get_db)):
    return [resource_context.ref(r) for r in resource_context.lookup(db,q)]
