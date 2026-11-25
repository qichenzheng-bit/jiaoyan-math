from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user
from app.models import ChatMessage, ChatSession, IntakeJob
router=APIRouter(prefix="/tasks",dependencies=[Depends(current_user)])
@router.get("")
def listing(db:Session=Depends(get_db)):
    rows=[{"id":j.id,"kind":"intake","title":j.title,"state":j.state,"created_at":j.created_at,"detail":j.detail,"session_id":None} for j in db.scalars(select(IntakeJob).order_by(IntakeJob.created_at.desc()).limit(100))]
    rows.extend({"id":m.id,"kind":"chat","title":s.title,"state":m.state,"created_at":m.created_at,"detail":m.detail,"session_id":s.id} for m,s in db.execute(select(ChatMessage,ChatSession).join(ChatSession,ChatSession.id==ChatMessage.session_id).where(ChatMessage.role=="assistant").order_by(ChatMessage.created_at.desc()).limit(100)))
    return sorted(rows,key=lambda x:x["created_at"],reverse=True)[:100]
