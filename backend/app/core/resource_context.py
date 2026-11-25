"""Retrieve real records only, with bounded context."""
from sqlalchemy import select,or_
from fastapi import HTTPException
from app.models import TeachingResource as R
def ref(r):
    return {"id":r.id,"code":r.code,"kind":r.kind,"title":r.title}
def lookup(db,q,limit=12):
    q=q.strip()
    if not q:return []
    return list(db.scalars(select(R).where(R.archived==False,or_(R.code==q.upper(),R.title.contains(q,autoescape=True),R.content.contains(q,autoescape=True))).order_by(R.updated_at.desc(),R.id).limit(limit)))
def prepare(db,ids,query):
    rows=[]
    for id in dict.fromkeys(ids):
        r=db.get(R,id)
        if not r or r.archived:raise HTTPException(422,"引用资源不存在或已归档")
        rows.append(r)
    if query:
        rows.extend(r for r in lookup(db,query,6) if r.id not in {x.id for x in rows})
    rows=rows[:10]
    parts=[]
    used=[]
    size=0
    for r in rows:
        value=f"[{r.code}] {r.title}\n正文：{r.content[:2200]}\n答案：{r.answer[:600]}\n解析：{r.solution[:1600]}\n证明：{r.proof[:1000]}"
        if size+len(value)>18000:break
        used.append(ref(r));parts.append(value);size+=len(value)
    return used,"\n\n".join(parts)
