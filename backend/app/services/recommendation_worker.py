"""Process persisted recommendation requests after committed question changes."""
import asyncio
import json
import logging
import os
from sqlalchemy import select
from fastapi import HTTPException
from app.core.db import session_factory
from app.core.security import now
from app.models import Setting, TeachingResource, User
from app.api import resources as bank

logger=logging.getLogger(__name__)
PREFIX="question.recommendation."

def pending():
    jobs=[]
    with session_factory()() as db:
        for key,value in db.execute(select(Setting.key,Setting.value).where(Setting.key.startswith(PREFIX))):
            try:s=json.loads(value)
            except (ValueError,TypeError):continue
            if not isinstance(s,dict) or s.get("state") not in ("queued","running") or not s.get("user_id"):continue
            if s.get("next_attempt_at",0)>now():continue
            jobs.append((s.get("state")!="running",s.get("created_at",0),key[len(PREFIX):],s["user_id"]))
    return sorted(jobs)

def process_one(ident,user_id):
    with session_factory()() as db:
        user=db.get(User,user_id)
        if user is None:return
        bank.admin_lock(db,user)
        row=db.get(TeachingResource,ident,with_for_update=True)
        if row is None:return
        state=bank.read_recommendation(db,row)
        if not state:
            # Resource revision changed; never apply a recommendation to stale content.
            old=db.get(Setting,bank.recommendation_key(ident))
            if old:
                try:old_state=json.loads(old.value)
                except (ValueError,TypeError):old_state={}
                if isinstance(old_state,dict) and old_state.get("state") in ("queued","running"):
                    bank.store_recommendation(db,row,{"revision":row.revision,"state":"failed","reason":"题目版本已更新，请重新比较解法"})
                    db.commit()
            return
        if row.archived:
            bank.store_recommendation(db,row,{**state,"state":"failed","reason":"题目已归档"})
            db.commit();return
        if state.get("state") not in ("queued","running") or state.get("next_attempt_at",0)>now():return
        revision=bank.RecommendationStart(revision=row.revision)
        try:
            if state["state"]=="queued":bank.start_recommendation(ident,revision,db,user)
            else:bank.poll_recommendation(ident,revision,db,user)
        except HTTPException as exc:
            # Keep old recommendation and original solutions. Retry temporary worker unavailability only.
            attempts=state.get("attempts",0)+1
            if state["state"]=="running" and now()-state.get("created_at",0)<=300 and exc.status_code in (409,502,503,504):
                bank.store_recommendation(db,row,{**state,"next_attempt_at":now()+15})
            elif state["state"]=="queued" and attempts<3 and exc.status_code in (409,502,503,504):
                bank.store_recommendation(db,row,{**state,"attempts":attempts,"next_attempt_at":now()+60})
            else:
                bank.store_recommendation(db,row,{**state,"state":"failed","reason":"AI 评价未完成，请检查模型登录状态后重试"})
            db.commit()

def process_pending(limit=4):
    for _,_,ident,user_id in pending()[:limit]:
        try:process_one(ident,user_id)
        except Exception as exc:logger.warning("Recommendation task deferred: %s",type(exc).__name__)

async def recommendation_loop():
    if os.environ.get("WG_RECOMMENDATION_SCHEDULER")=="0":return
    await asyncio.sleep(12)
    while True:
        try:await asyncio.to_thread(process_pending)
        except Exception as exc:logger.warning("Recommendation queue unavailable: %s",type(exc).__name__)
        await asyncio.sleep(12)
