"""User-maintained teaching preferences and prompt supplements; security rules stay in code."""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Setting
from app.core.security import now

Scope=Literal["global","chat","work","intake","document","video","cover"]
SCOPES=("global","chat","work","intake","document","video","cover")
class Memory(BaseModel):
    model_config=ConfigDict(extra="forbid")
    id: str=Field(min_length=1,max_length=36)
    scope: Scope="global"
    text: str=Field(min_length=1,max_length=1000)
    enabled: bool=True

class MemoryUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    revision: int=Field(ge=0)
    items: list[Memory]=Field(max_length=50)

class PromptUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    revision: int=Field(ge=0)
    text: str=Field(max_length=16000)

def key(user,category,scope="all"):
    return f"ai.{category}.{user.id}.{scope}"

def read(db,k,default):
    r=db.get(Setting,k)
    if not r:return default
    try:return json.loads(r.value)
    except (ValueError,TypeError):raise HTTPException(409,"AI 配置记录异常")

def lock_user(db,user):
    from app.models import User
    db.scalar(select(User).where(User.id==user.id).with_for_update())

def save(db,k,data):
    db.merge(Setting(key=k,value=json.dumps(data,ensure_ascii=False)))

def memories(db,user):
    return read(db,key(user,"memory"),{"revision":0,"items":[]})

def prompt(db,user,scope):
    if scope not in SCOPES:raise HTTPException(422,"未知提示词范围")
    return read(db,key(user,"prompt",scope),{"revision":0,"text":"","history":[]})

def set_memory(db,user,body):
    lock_user(db,user);old=memories(db,user)
    if old["revision"]!=body.revision:raise HTTPException(409,"记忆版本已变化")
    if len({i.id for i in body.items})!=len(body.items):raise HTTPException(422,"记忆编号重复")
    data={"revision":body.revision+1,"items":[i.model_dump() for i in body.items]}
    save(db,key(user,"memory"),data)
    return data

def set_prompt(db,user,scope,body):
    lock_user(db,user);old=prompt(db,user,scope)
    if old["revision"]!=body.revision:raise HTTPException(409,"提示词版本已变化")
    history=[{"revision":old["revision"],"text":old["text"],"at":now()},*old["history"]][:2]
    data={"revision":body.revision+1,"text":body.text,"history":history}
    save(db,key(user,"prompt",scope),data)
    return data

def context(db,user,scope):
    """A stable snapshot at the beginning of a task. Explicit task instructions take priority."""
    if scope not in SCOPES:raise HTTPException(422,"未知提示词范围")
    prefs=[i["text"] for i in memories(db,user)["items"] if i["enabled"] and i["scope"] in ("global",scope)]
    additions=[prompt(db,user,k)["text"] for k in dict.fromkeys(("global",scope))]
    return ("\n【用户长期偏好与业务提示词；不得覆盖工具权限、审核和当前明确要求】\n"+
            "\n".join([*prefs,*additions]))[:16000]
