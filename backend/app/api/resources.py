from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, audit, now
from app.core.solution_methods import normalize_subject, MATH_SUBJECTS, parse_methods, recommended_solution
from app.core.content_normalization import question_fingerprint, unit_fingerprint
from app.models import TeachingResource, User

router = APIRouter(prefix="/resources", tags=["resources"], dependencies=[Depends(current_user)])
Kind = Literal["question", "knowledge", "source"]
class Draft(BaseModel):
    kind: Kind
    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(default="", max_length=40)
    content: str = Field(min_length=1, max_length=50000)
    answer: str = Field(default="", max_length=20000)
    solution: str = Field(default="", max_length=50000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source_id: str | None = Field(default=None, max_length=36)

def clean(body: Draft, db: Session):
    d = body.model_dump()
    for key in ("title","content"):
        if not d[key].strip():
            raise HTTPException(422, "标题和内容不能为空")
    d["title"] = d["title"].strip()
    d["subject"] = normalize_subject(d["subject"])
    if any(len(t)>60 for t in d["tags"]):
        raise HTTPException(422,"标签最多60字")
    d["tags"] = list(dict.fromkeys(t.strip() for t in d["tags"] if t.strip()))
    if body.kind != "question":
        d["answer"] = d["solution"] = ""
    if body.source_id:
        source = db.get(TeachingResource, body.source_id)
        if body.kind == "source" or not source or source.kind != "source" or source.archived:
            raise HTTPException(422,"来源资料不存在或已归档")
    d["fingerprint"] = (question_fingerprint(d["content"],d["solution"],d["answer"]) if body.kind=="question" else unit_fingerprint(d["title"],d["content"]))
    return d

def view(row):
    result = {key:getattr(row,key) for key in ("id","kind","title","subject","content","answer","solution","tags","source_id","archived","created_at","updated_at")}
    return result

@router.get("/subjects")
def subjects():
    return list(MATH_SUBJECTS)

@router.get("")
def listing(kind: Kind | None=None, subject: str="", q: str=Query("",max_length=200), archived: bool=False, limit: int=Query(30,ge=1,le=100), offset: int=Query(0,ge=0), db: Session=Depends(get_db)):
    filters=[TeachingResource.archived==archived]
    if kind: filters.append(TeachingResource.kind==kind)
    if subject: filters.append(TeachingResource.subject==normalize_subject(subject))
    if q.strip(): filters.append(or_(TeachingResource.title.contains(q.strip(),autoescape=True),TeachingResource.content.contains(q.strip(),autoescape=True)))
    total=db.scalar(select(func.count()).select_from(TeachingResource).where(*filters))
    rows=db.scalars(select(TeachingResource).where(*filters).order_by(TeachingResource.updated_at.desc(),TeachingResource.id).offset(offset).limit(limit))
    return {"items":[view(r) for r in rows],"total":total}

@router.post("/duplicates", dependencies=[Depends(require_origin)])
def duplicates(body: Draft, db: Session=Depends(get_db)):
    d=clean(body,db)
    rows=db.scalars(select(TeachingResource).where(TeachingResource.kind==body.kind,TeachingResource.fingerprint==d["fingerprint"]).limit(20))
    return [view(r) for r in rows]

@router.post("", dependencies=[Depends(require_origin)])
def create(body: Draft, db: Session=Depends(get_db), user: User=Depends(current_user)):
    d=clean(body,db)
    row=TeachingResource(id=str(uuid4()),**d,archived=False,created_at=now(),updated_at=now())
    db.add(row);audit(db,"resource.create",user.id);db.commit()
    return view(row)

def existing(db,id):
    row=db.get(TeachingResource,id)
    if not row: raise HTTPException(404,"资源不存在")
    return row

@router.put("/{id}", dependencies=[Depends(require_origin)])
def update(id: str, body: Draft, db: Session=Depends(get_db), user: User=Depends(current_user)):
    row=existing(db,id)
    if row.kind!=body.kind or row.archived:
        raise HTTPException(409,"不能修改资源类型或已归档资源")
    for k,v in clean(body,db).items(): setattr(row,k,v)
    row.updated_at=now();audit(db,"resource.update",user.id);db.commit()
    return view(row)

@router.post("/{id}/archive", dependencies=[Depends(require_origin)])
def archive(id:str, db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=existing(db,id);row.archived=True;row.updated_at=now();audit(db,"resource.archive",user.id);db.commit()
    return view(row)

@router.post("/{id}/restore", dependencies=[Depends(require_origin)])
def restore(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=existing(db,id);row.archived=False;row.updated_at=now();audit(db,"resource.restore",user.id);db.commit()
    return view(row)

@router.get("/{id}/methods")
def methods(id:str,db:Session=Depends(get_db)):
    row=existing(db,id)
    return {"methods":parse_methods(row.solution),"recommended":recommended_solution(row.solution)}
