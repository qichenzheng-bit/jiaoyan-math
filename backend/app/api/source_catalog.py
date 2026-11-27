"""Structured source metadata. The original source and all associations remain unchanged."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, text
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


class StatisticsRequest(BaseModel):
    source_ids:list[str]=Field(default_factory=list,max_length=1000)
    years:list[str]=Field(default_factory=list,max_length=100)
    institutions:list[str]=Field(default_factory=list,max_length=100)
    categories:list[str]=Field(default_factory=list,max_length=100)
    exam_types:list[str]=Field(default_factory=list,max_length=100)
    source_types:list[str]=Field(default_factory=list,max_length=20)
    subject:str=Field(default="",max_length=40)
    all_sources:bool=False
    limit:int=Field(default=50,ge=1,le=100)
    offset:int=Field(default=0,ge=0)

@router.post("/statistics",dependencies=[Depends(require_origin)])
def statistics(body:StatisticsRequest,db:Session=Depends(get_db)):
    """Count recorded question knowledge names, not graph labels or inferred source totals."""
    if not (body.all_sources or body.source_ids or body.years or body.institutions or body.categories or body.exam_types or body.source_types):
        raise HTTPException(422,"请选择统计来源或明确选择全部来源")
    filters=["s.kind='source'","s.archived=false"]
    params={"limit":body.limit,"offset":body.offset}
    for key,col,maxlen in (("source_ids","s.id",36),("years","s.cohort_year",12),
                            ("institutions","d.institution",120),("categories","d.category",60),
                            ("exam_types","s.exam_type",80),("source_types","s.source_type",16)):
        values=list(dict.fromkeys(v.strip() for v in getattr(body,key) if v.strip()))
        if getattr(body,key) and not values or any(len(v)>maxlen for v in values):
            raise HTTPException(422,"统计筛选条件无效")
        if values:
            filters.append(col+" = ANY(CAST(:"+key+" AS varchar[]))")
            params[key]=values
    subject_filter=""
    if body.subject.strip():
        subject_filter=" AND q.subject=:subject"
        params["subject"]=normalize_subject(body.subject.strip())
    cte="""
    WITH selected AS (
        SELECT s.id,coalesce(d.intake_status,'unknown') AS intake_status
        FROM teaching_resources s LEFT JOIN source_catalog_details d ON d.source_id=s.id
        WHERE """+" AND ".join(filters)+"""
    ), pairs AS (
        SELECT l.resource_id AS question_id,l.source_id
        FROM resource_source_links l JOIN selected s ON s.id=l.source_id
        JOIN teaching_resources q ON q.id=l.resource_id
        WHERE q.kind='question' AND q.archived=false"""+subject_filter+"""
        UNION
        SELECT q.id,q.source_id FROM teaching_resources q JOIN selected s ON s.id=q.source_id
        WHERE q.kind='question' AND q.archived=false"""+subject_filter+"""
    ), questions AS (
        SELECT DISTINCT question_id FROM pairs
    ), names AS (
        SELECT DISTINCT q.id AS question_id,q.subject,btrim(n.name) AS name
        FROM questions x JOIN teaching_resources q ON q.id=x.question_id
        CROSS JOIN LATERAL jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(CAST(q.tags AS jsonb))='array'
            THEN CAST(q.tags AS jsonb) ELSE '[]'::jsonb END
        ) AS n(name)
        WHERE btrim(n.name)<>''
    ), grouped AS (
        SELECT n.subject,n.name,count(DISTINCT n.question_id) AS question_count,
               count(*) AS source_question_count
        FROM names n JOIN pairs p ON p.question_id=n.question_id
        GROUP BY n.subject,n.name
    )
    """
    # One statement gives all counts a consistent snapshot. A source-question pair
    # is not a physical page occurrence; multiple roles and legacy primary links are deduplicated.
    query=cte+"""
    SELECT (SELECT count(*) FROM selected) AS source_count,
           (SELECT count(*) FROM selected WHERE intake_status='completed') AS confirmed_complete_sources,
           (SELECT count(*) FROM questions) AS question_count,
           (SELECT count(*) FROM pairs) AS source_question_count,
           (SELECT count(DISTINCT question_id) FROM names) AS questions_with_knowledge,
           (SELECT count(*) FROM grouped) AS knowledge_count,
           coalesce((SELECT jsonb_agg(to_jsonb(g) ORDER BY g.question_count DESC,g.subject,g.name)
                     FROM (SELECT * FROM grouped ORDER BY question_count DESC,subject,name
                           LIMIT :limit OFFSET :offset) g),'[]'::jsonb) AS items
    """
    result=dict(db.execute(text(query),params).mappings().one())
    return {**result,"limit":body.limit,"offset":body.offset,"scope":"recorded_questions_only",
            "count_unit":"distinct_source_question_pairs","original_question_total":None}
