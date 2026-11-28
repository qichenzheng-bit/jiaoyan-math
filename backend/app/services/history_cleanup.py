"""One-time owner-authorized historical work cleanup, never a recurring retention policy.

Run while the application service is stopped by the deployment lock. The
existing deletion service preserves registered resources, formal documents,
original files, and independent video projects. Unconverted drafts and
workspace batch progress are part of the deleted historical work.
"""
import argparse
import json

from fastapi import HTTPException
from sqlalchemy import select
from app.core.db import session_factory
from app.core.security import audit
from app.models import Setting, User, WorkSession, IntakeJob, IntakeSupplement
from app.services import work_removal
from app.api import qoder, video

KEY = "system.native_work_history_cleanup.v1"
# Last known commit before the owner's cleanup request (2026-11-28 00:51:11 UTC).
# Never select a workspace created or modified after this boundary.
CUTOFF = 1795827071

def eligible(s):
    return (s.created_at <= CUTOFF and s.updated_at <= CUTOFF
            and not any(r.get("state") == "running" or
                        r.get("phase") == "executing" and r.get("state") == "cancelled"
                        for r in (s.agent_history or [])))

def active_video(db,s):
    for r in s.agent_history or []:
        children=[r.get("child") or {},*[x.get("video_child") or {} for x in r.get("steps",[])]]
        for child in children:
            if child.get("kind")!="video" or not child.get("id"):continue
            try:result=video.job_read(child["project"],child["id"],db)
            except HTTPException as exc:
                if exc.status_code==404:continue
                raise
            if result.get("status") not in ("succeeded","failed","cancelled","canceled","stopped"):return True
    return False

def candidates(db):
    return [s.id for s in db.scalars(select(WorkSession).where(
        WorkSession.created_at<=CUTOFF,WorkSession.updated_at<=CUTOFF).order_by(WorkSession.id))
        if eligible(s)]

def status(db):
    if db.get(Setting,KEY):return "done"
    return "pending" if candidates(db) else "empty"

def cleanup(db):
    if db.get(Setting,KEY):return {"state":"done","already_completed":True}
    ids=candidates(db)
    if not ids:
        db.merge(Setting(key=KEY,value=json.dumps({"deleted":0,"skipped":0})))
        db.commit()
        return {"state":"done","deleted":0,"skipped":0}
    # Avoid stopping any real inference or supplement as a side effect of cleanup.
    if db.scalar(select(IntakeJob.id).where(IntakeJob.state=="running").limit(1)) or db.scalar(select(IntakeSupplement.id).where(IntakeSupplement.state=="running").limit(1)):
        return {"state":"deferred","reason":"active_intake"}
    worker=qoder.request("GET","/status")
    if worker.get("busy") or worker.get("waiting_count") or (worker.get("login") or {}).get("state") in ("starting","waiting"):
        return {"state":"deferred","reason":"active_worker"}
    user=db.get(User,1)
    if user is None:return {"state":"deferred","reason":"administrator_missing"}
    removed=skipped=0
    for ident in ids:
        s=db.get(WorkSession,ident,with_for_update=True)
        if s is None or not eligible(s):
            skipped+=1;db.rollback();continue
        try:
            if active_video(db,s):
                skipped+=1;db.rollback();continue
            work_removal.remove_workspace(db,s,user=user)
            audit(db,"work.history_cleanup",user.id)
            db.commit();removed+=1
        except HTTPException:
            db.rollback();skipped+=1
    result={"state":"done","deleted":removed,"skipped":skipped}
    # Mark the authorized operation complete: future releases never delete new work.
    db.merge(Setting(key=KEY,value=json.dumps(result)))
    db.commit()
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("status","cleanup"))
    args=parser.parse_args()
    with session_factory()() as db:
        if args.action=="status":print(status(db));return
        print(json.dumps(cleanup(db),ensure_ascii=False))

if __name__=="__main__":main()
