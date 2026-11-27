"""Structured source metadata. The original source and all associations remain unchanged."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, audit, now
from app.core.bank_history import record, history
from app.core.solution_methods import normalize_subject
from app.models import SourceCatalogDetail as Detail, TeachingResource as Resource, User
from app.api.resources import existing, admin_lock

router=APIRouter(prefix="/source-catalog",tags=["source-catalog"],dependencies=[Depends(current_user)])
class Draft(BaseModel):
    revision:int=Field(ge=0)
    category:str=Field(default="",max_length=60)
    institution:str=Field(default="",max_length=120)
    subject_code:str=Field(default="",max_length=40)
    subjects:list[str]=Field(default_factory=list,max_length=30)
    author:str=Field(default="",max_length=180)
    publisher:str=Field(default="",max_length=180)
    intake_status:Literal["unknown","not_started","in_progress","completed","stopped"]="unknown"

def source(db,id,lock=False):
    r=existing(db,id,lock)
    if r.kind!="source":raise HTTPException(422,"请选择来源资料")
    return r

def info(r,d):
    # Legacy data are preserved and only confirmed metadata are exposed.
    base={"source_id":r.id,"title":r.title,"code":r.code,"source_type":r.source_type,
          "year":r.cohort_year,"exam_type":r.exam_type,"edition":r.edition,"series_key":r.series_key,"archived":r.archived}
    if d is None:
        return {**base,"revision":0,"category":"","institution":"","subject_code":"","subjects":[r.subject] if r.subject else [],"author":"","publisher":"","intake_status":"unknown","updated_at":None}
    return {**base,**{k:getattr(d,k) for k in ("revision","category","institution","subject_code","subjects","author","publisher","intake_status","updated_at")}}

@router.get("/sources")
def listing(q:str=Query("",max_length=200),institutions:list[str]|None=Query(None),categories:list[str]|None=Query(None),
            years:list[str]|None=Query(None),exam_types:list[str]|None=Query(None),subject_codes:list[str]|None=Query(None),
            year_from:int|None=Query(None,ge=1900,le=2200),year_to:int|None=Query(None,ge=1900,le=2200),
            source_types:list[str]|None=Query(None),limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    if year_from and year_to and year_from>year_to:raise HTTPException(422,"年份范围无效")
    stmt=select(Resource,Detail).outerjoin(Detail,Detail.source_id==Resource.id).where(Resource.kind=="source",Resource.archived==False)
    for col,values in ((Detail.institution,institutions),(Detail.category,categories),(Resource.cohort_year,years),
                       (Resource.exam_type,exam_types),(Detail.subject_code,subject_codes),(Resource.source_type,source_types)):
        if values:
            if len(values)>200 or any(len(x)>180 for x in values):raise HTTPException(422,"筛选条件过多或过长")
            stmt=stmt.where(col.in_(values))
    if year_from is not None or year_to is not None:
        stmt=stmt.where(Resource.cohort_year.op("~")("^[0-9]{4}$"))
        if year_from is not None:stmt=stmt.where(Resource.cohort_year>=str(year_from))
        if year_to is not None:stmt=stmt.where(Resource.cohort_year<=str(year_to))
    if q.strip():
        term=q.strip()
        stmt=stmt.where(or_(*(c.contains(term,autoescape=True) for c in (Resource.title,Resource.code,Resource.series_key,Resource.exam_type,Detail.institution,Detail.subject_code,Detail.author))))
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=db.execute(stmt.order_by(Resource.cohort_year.desc(),Resource.title,Resource.id).offset(offset).limit(limit))
    return {"items":[info(r,d) for r,d in rows],"total":total}

@router.get("/sources/{id}")
def read(id:str,db:Session=Depends(get_db)):
    return info(source(db,id),db.get(Detail,id))

@router.put("/sources/{id}",dependencies=[Depends(require_origin)])
def update(id:str,body:Draft,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);r=source(db,id,True);d=db.get(Detail,id)
    if r.archived:raise HTTPException(409,"归档来源不可编辑")
    before=info(r,d)
    if before["revision"]!=body.revision:raise HTTPException(409,"来源属性版本已变化，请重新读取")
    if any(len(s.strip())>40 for s in body.subjects):raise HTTPException(422,"学科名称过长")
    values=body.model_dump(exclude={"revision"})
    values={k:v.strip() if isinstance(v,str) else v for k,v in values.items()}
    values["subjects"]=list(dict.fromkeys(normalize_subject(s) for s in body.subjects if s.strip()))
    if d is None:
        d=Detail(source_id=id);db.add(d)
    for k,v in values.items():setattr(d,k,v)
    d.revision=body.revision+1;d.updated_at=now()
    db.flush();after=info(r,d)
    record(db,id,"source_catalog_update",before,after,user.id,d.revision)
    audit(db,"source_catalog.update",user.id);db.commit()
    return after

@router.get("/sources/{id}/history")
def changes(id:str,db:Session=Depends(get_db)):
    source(db,id)
    return {"items":[row for row in history(db,id) if row["kind"]=="source_catalog_update"]}
