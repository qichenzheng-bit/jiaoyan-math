"""Append-only history, separate from mutable resource fields."""
import json
from uuid import uuid4
from sqlalchemy import select
from app.models import Setting
from app.core.security import now

def record(db,resource_id,kind,before,after,user_id,revision):
    key="bank.history."+resource_id+"."+str(uuid4())
    db.add(Setting(key=key,value=json.dumps({"id":key,"kind":kind,"before":before,"after":after,"user_id":user_id,"revision":revision,"created_at":now()},ensure_ascii=False)))

def history(db,resource_id):
    rows=[]
    for s in db.scalars(select(Setting).where(Setting.key.startswith("bank.history."+resource_id+"."))):
        rows.append(json.loads(s.value))
    return sorted(rows,key=lambda x:(x["revision"],x["created_at"],x["id"]),reverse=True)
