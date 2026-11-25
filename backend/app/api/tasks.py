from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin
from app.models import ChatMessage, ChatSession, IntakeJob, DocumentAiEdit, TeachingDocument
from app.api import chat, intelligence, documents
router=APIRouter(prefix="/tasks",dependencies=[Depends(current_user)])
@router.get("")
def listing(db:Session=Depends(get_db)):
    rows=[{"id":j.id,"kind":"intake","title":j.title,"state":j.state,"created_at":j.created_at,"detail":j.detail,"session_id":None} for j in db.scalars(select(IntakeJob).order_by(IntakeJob.created_at.desc()).limit(100))]
    rows.extend({"id":m.id,"kind":"chat","title":s.title,"state":m.state,"created_at":m.created_at,"detail":m.detail,"session_id":s.id} for m,s in db.execute(select(ChatMessage,ChatSession).join(ChatSession,ChatSession.id==ChatMessage.session_id).where(ChatMessage.role=="assistant").order_by(ChatMessage.created_at.desc()).limit(100)))
    rows.extend({"id":e.id,"kind":"document_ai","title":d.title,"state":e.state,"created_at":e.created_at,"detail":e.detail,"session_id":None,"document_id":d.id,"document_kind":d.kind} for e,d in db.execute(select(DocumentAiEdit,TeachingDocument).join(TeachingDocument,TeachingDocument.id==DocumentAiEdit.document_id).order_by(DocumentAiEdit.created_at.desc()).limit(100)))
    return sorted(rows,key=lambda x:x["created_at"],reverse=True)[:100]

@router.post("/sync",dependencies=[Depends(require_origin)])
def sync_running(db:Session=Depends(get_db)):
    # Do not issue unbounded socket requests if the worker is offline.
    from app.api import qoder
    try: status=qoder.request("GET","/status")
    except HTTPException:
        return {"synced":0,"worker_available":False}
    if not status.get("chat_available"):return {"synced":0,"worker_available":False}
    chats=list(db.scalars(select(ChatMessage.id).where(ChatMessage.role=="assistant",ChatMessage.state=="running").order_by(ChatMessage.created_at).limit(4)))
    jobs=list(db.scalars(select(IntakeJob.id).where(IntakeJob.state=="running").order_by(IntakeJob.created_at).limit(4)))
    for ident in chats:
        m=db.scalar(select(ChatMessage).where(ChatMessage.id==ident).with_for_update())
        if m:chat.sync(db,m);db.commit()
    for ident in jobs:
        j=intelligence.get_job(db,ident);intelligence.sync(db,j);db.commit()
    edits=list(db.execute(select(DocumentAiEdit.document_id,DocumentAiEdit.id).where(DocumentAiEdit.state=="running").order_by(DocumentAiEdit.created_at).limit(2)))
    for doc_id,ident in edits:
        documents.row(db,doc_id);e=documents.ai_find(db,doc_id,ident);documents.sync_ai_edit(db,e);db.commit()
    return {"synced":len(chats)+len(jobs)+len(edits),"worker_available":True}
