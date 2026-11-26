"""Persistent opt-in Qoder CN check-in scheduler, independent of AI usage."""
import asyncio
import json
import logging
import threading
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session
from app.core.db import get_db, session_factory
from app.core.security import current_user, require_origin, audit
from app.models import Setting, User
from app.services import qoder_campaign as provider

router=APIRouter(prefix="/qiandao",dependencies=[Depends(current_user)])
KEY="qiandao.qoder_cn.v1"
LOCK=threading.Lock()
log=logging.getLogger(__name__)
MAX_ATTEMPTS=3
RETRY_SECONDS=900
TERMINAL={"claimed","already_claimed","not_claimable","no_verified_campaign","ambiguous_campaign","authorization_denied","endpoint_unavailable","upstream_rejected","pat_missing","pat_invalid","pat_permissions","unexpected_response"}

def read_state(db):
    row=db.get(Setting,KEY)
    if row:
        try:
            data=json.loads(row.value)
            if isinstance(data,dict):return data
        except (ValueError,TypeError):pass
    return {"enabled":False,"history":[]}

def write_state(db,state):
    db.merge(Setting(key=KEY,value=json.dumps(state,ensure_ascii=False)))
    db.commit()

def view(db):
    state=read_state(db)
    start,end=provider.round_window()
    configured=True
    reason=None
    try:provider.read_pat()
    except provider.CampaignError as exc:
        configured=False;reason=exc.code
    current=state.get("last")
    if not isinstance(current,dict) or current.get("round")!=start.date().isoformat():current=None
    return {"enabled":state.get("enabled") is True,"configured":configured,"reason":reason,
            "round":start.date().isoformat(),"next_round":end.isoformat(),
            "current":current,"history":state.get("history",[])[:30],
            "quota":state.get("quota"),"quota_error":state.get("quota_error"),
            "changes":state.get("changes",[])[:200],
            "daily":state.get("daily") if (state.get("daily") or {}).get("day")==provider.datetime.now(provider.CN).date().isoformat() else None}

def attempt(db, *, manual=False, epoch=None):
    # Existing production service uses a single process. Serialize manual and scheduled calls.
    with LOCK:
        state=read_state(db)
        start,end=provider.round_window()
        day=start.date().isoformat()
        timestamp=time.time() if epoch is None else epoch
        last=state.get("last") or {}
        if last.get("round")!=day:last={}
        if last.get("state") in ("claimed","already_claimed"):
            return view(db)
        if not manual:
            if state.get("enabled") is not True or timestamp<start.timestamp()+300:return view(db)
            if last.get("state") in TERMINAL or last.get("attempts",0)>=MAX_ATTEMPTS:return view(db)
            if timestamp-last.get("at",0)<RETRY_SECONDS:return view(db)
        elif last.get("at") and timestamp-last["at"]<60:
            raise HTTPException(409,"请至少间隔 60 秒再试")
        # Persist intent before external mutation so crashes do not create an immediate duplicate.
        record={"round":day,"state":"pending","earned":None,"at":timestamp,"attempts":last.get("attempts",0)+1,
                "mode":"manual" if manual else "auto"}
        state["last"]=record
        write_state(db,state)
        try:
            result=provider.run_claim()
            record.update(result)
        except provider.CampaignError as exc:
            record["state"]=exc.code
        except Exception:
            record["state"]="upstream_unavailable"
            log.warning("Qoder check-in attempt failed without exposing provider details")
        # Replace the round's history entry rather than accumulating retries as rewards.
        state["history"]=[record]+[v for v in state.get("history",[]) if v.get("round")!=day][:29]
        state["last"]=record
        write_state(db,state)
        return view(db)

@router.get("/state")
def status(db:Session=Depends(get_db)):
    return view(db)

class AutoPreference(BaseModel):
    enabled:bool

@router.post("/auto",dependencies=[Depends(require_origin)])
def auto(body:AutoPreference,db:Session=Depends(get_db),user:User=Depends(current_user)):
    with LOCK:
        if body.enabled:
            try:provider.read_pat()
            except provider.CampaignError:raise HTTPException(422,"请先在签到助手配置 Qoder CN PAT")
        state=read_state(db)
        state["enabled"]=body.enabled
        audit(db,"qiandao.auto.update",user.id)
        write_state(db,state)
        return view(db)

@router.post("/run",dependencies=[Depends(require_origin)])
def run(db:Session=Depends(get_db),user:User=Depends(current_user)):
    try:provider.read_pat()
    except provider.CampaignError:raise HTTPException(422,"请先在服务器配置独立 Qoder CN PAT")
    audit(db,"qiandao.run",user.id)
    db.commit()
    return attempt(db,manual=True)

def apply_snapshot(state,snapshot):
    """Ledger records observed net changes only, not inferred transactions."""
    old=state.get("quota")
    day=provider.datetime.fromtimestamp(snapshot["at"],provider.CN).date().isoformat()
    daily=state.get("daily")
    if not daily or daily.get("day")!=day:
        daily={"day":day,"increase":0,"decrease":0,"intervals":0}
    if old and snapshot["at"]>old["at"]:
        before={p["kind"] for p in old["packs"]}
        after={p["kind"] for p in snapshot["packs"]}
        delta=round(snapshot["balance"]-old["balance"],6)
        # A changed pack set may be incomplete, so establish a new baseline.
        if before==after:
            daily["intervals"]+=1
            if delta:
                entry={"at":snapshot["at"],"from_at":old["at"],"delta":delta,"balance":snapshot["balance"]}
                state["changes"]=[entry]+state.get("changes",[])[:199]
                key="increase" if delta>0 else "decrease"
                daily[key]=round(daily[key]+abs(delta),6)
    state["daily"]=daily
    state["quota"]=snapshot
    state.pop("quota_error",None)

def refresh_quota(db,*,force=False):
    with LOCK:
        state=read_state(db)
        now=time.time()
        if now-state.get("quota_attempt_at",0)<(15 if force else 60):
            return view(db)
        state["quota_attempt_at"]=now
        try:
            provider.read_pat()
            apply_snapshot(state,provider.quota_snapshot())
        except provider.CampaignError as exc:
            state["quota_error"]=exc.code
        write_state(db,state)
        return view(db)

class PatInput(BaseModel):
    pat:SecretStr=Field(min_length=11,max_length=4096)

@router.post("/pat",dependencies=[Depends(require_origin)])
def configure_pat(body:PatInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    with LOCK:
        value=body.pat.get_secret_value().strip()
        try:
            try:old=provider.read_pat()
            except provider.CampaignError:old=None
            provider.save_pat(value)
        except provider.CampaignError as exc:
            raise HTTPException(422,{"pat_invalid":"PAT 格式不正确","authorization_denied":"平台拒绝 PAT 授权"}.get(exc.code,"PAT 验证失败，请检查授权或稍后再试")) from None
        except OSError:
            raise HTTPException(503,"服务器无法保存 PAT") from None
        state=read_state(db)
        if old!=value:
            archive=state.get("archives",[])
            previous={k:state[k] for k in ("history","last","changes","quota","daily") if k in state}
            if previous:archive=[previous]+archive
            state={"enabled":False,"history":[],"archives":archive[:5]}
        audit(db,"qiandao.pat.update",user.id)
        write_state(db,state)
        return view(db)

@router.delete("/pat",dependencies=[Depends(require_origin)])
def remove_pat(db:Session=Depends(get_db),user:User=Depends(current_user)):
    with LOCK:
        state=read_state(db)
        state["enabled"]=False
        state["quota_error"]="pat_missing"
        audit(db,"qiandao.pat.remove",user.id)
        write_state(db,state)
        try:provider.PAT_FILE.unlink(missing_ok=True)
        except OSError:raise HTTPException(503,"无法删除 PAT，自动领取已关闭") from None
        return view(db)

@router.post("/quota/refresh",dependencies=[Depends(require_origin)])
def quota_refresh(db:Session=Depends(get_db)):
    return refresh_quota(db,force=True)

def tick():
    with session_factory()() as db:
        state=read_state(db)
        if state.get("enabled") is True:attempt(db)
        try:provider.read_pat()
        except provider.CampaignError:return
        refresh_quota(db)

async def scheduler():
    await asyncio.sleep(30)
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:
            log.warning("Qoder check-in scheduler deferred")
        await asyncio.sleep(60)
