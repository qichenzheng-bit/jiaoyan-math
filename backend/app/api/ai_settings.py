from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, audit
from app.core import ai_preferences as prefs
from app.models import User

router=APIRouter(prefix="/ai-settings",dependencies=[Depends(current_user)])

@router.get("/memory")
def memory(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return prefs.memories(db,user)

@router.put("/memory",dependencies=[Depends(require_origin)])
def update_memory(body:prefs.MemoryUpdate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    data=prefs.set_memory(db,user,body);audit(db,"ai.memory.update",user.id);db.commit();return data

@router.get("/prompts/{scope}")
def prompt(scope:prefs.Scope,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return prefs.prompt(db,user,scope)

@router.put("/prompts/{scope}",dependencies=[Depends(require_origin)])
def update_prompt(scope:prefs.Scope,body:prefs.PromptUpdate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    data=prefs.set_prompt(db,user,scope,body);audit(db,"ai.prompt.update",user.id);db.commit();return data
