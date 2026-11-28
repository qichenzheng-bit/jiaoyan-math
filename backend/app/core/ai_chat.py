"""Read-only model-directed retrieval in chat, with bounded persisted tool traces."""
import json
from fastapi import HTTPException
from app.models import Setting, TeachingResource
from app.core.resource_context import ref
from app.api import qoder

def key(mid):return "ai.chat.active."+mid

def load(db,m):
    row=db.get(Setting,key(m.id))
    return json.loads(row.value) if row else None

def store(db,m,state):
    db.merge(Setting(key=key(m.id),value=json.dumps(state,ensure_ascii=False)))

def trace(db,m):
    state=load(db,m)
    return [{"tool":x["tool"],"state":x["state"],"detail":x.get("detail","")} for x in state.get("steps",[])] if state else []

def stop_job(db,m):
    state=load(db,m)
    if state and state.get("phase")=="pending":
        # A start response may have been lost: release either a queued ID or
        # an accepted model call before discarding the application task.
        try:qoder.request("POST","/chat/"+state["job"]+"/cancel",{})
        except HTTPException as exc:
            if exc.status_code!=404:raise
        m.state="stopped"
        if state.get("native"):
            from app.core import native_chat
            native_chat.finish(db,m,state)
        else:finish(db,m,state)
        return None
    return state["job"] if state else m.id

def finish(db,m,state):
    state={k:v for k,v in state.items() if k in ("job","phase","steps")}
    state["phase"]="terminal"
    state["steps"]=[{"tool":x["tool"],"state":x["state"],"detail":x.get("detail","")} for x in state.get("steps",[])]
    store(db,m,state)

def add_refs(db,m,value):
    rows=value if isinstance(value,list) else value.get("items",[]) if isinstance(value,dict) else []
    if isinstance(value,dict) and value.get("id"):rows=[value,*rows]
    refs=list(m.resource_refs or [])
    seen={r["id"] for r in refs}
    for row in rows[:100]:
        if not isinstance(row,dict) or not isinstance(row.get("id"),str):continue
        item=db.get(TeachingResource,row["id"])
        if item and not item.archived and item.id not in seen:
            refs.append(ref(item));seen.add(item.id)
        if len(refs)>=10:break
    m.resource_refs=refs[:10]

def sync(db,m,state):
    if state.get("native"):
        from app.core import native_chat
        return native_chat.sync(db,m,state)
    retire_old(db,m,state)

def retire_old(db,m,state=None):
    if m.state!="running":return
    try:qoder.request("POST","/chat/"+(state["job"] if state and state.get("job") else m.id)+"/cancel",{})
    except HTTPException as exc:
        if exc.status_code!=404:return
    m.state="failed";m.detail="旧AI引擎已移除；历史消息保留，请重新提问"
    if state:finish(db,m,state)
