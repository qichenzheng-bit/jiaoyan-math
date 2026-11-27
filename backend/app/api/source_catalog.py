"""Structured source metadata. The original source and all associations remain unchanged."""
import csv
import io
import json
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, text
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, audit, now
from app.core.bank_history import record, history
from app.core.solution_methods import normalize_subject
from app.models import SourceCatalogDetail as Detail, TeachingResource as Resource, User, Setting
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

def statistics_scope(body:StatisticsRequest):
    """Shared selection for aggregation, reports and drill-down."""
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
        SELECT s.id,coalesce(d.intake_status,'unknown') AS intake_status,
               s.cohort_year,coalesce(d.institution,'') AS institution,s.exam_type
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
    return cte,params

@router.post("/statistics",dependencies=[Depends(require_origin)])
def statistics(body:StatisticsRequest,db:Session=Depends(get_db)):
    cte,params=statistics_scope(body)
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


class StatisticsQuestions(StatisticsRequest):
    knowledge_name:str=Field(min_length=1,max_length=180)
    knowledge_subject:str=Field(default="",max_length=40)

@router.post("/statistics/questions",dependencies=[Depends(require_origin)])
def statistics_questions(body:StatisticsQuestions,db:Session=Depends(get_db)):
    cte,params=statistics_scope(body)
    params.update(knowledge_name=body.knowledge_name.strip(),knowledge_subject=body.knowledge_subject)
    query=cte+"""
    , matched AS (
        SELECT q.id,q.code,q.title,q.subject,q.question_type,q.revision,q.updated_at,
               count(*) AS source_count
        FROM names n JOIN teaching_resources q ON q.id=n.question_id
        JOIN pairs p ON p.question_id=q.id
        WHERE n.name=:knowledge_name AND n.subject=:knowledge_subject
        GROUP BY q.id
    )
    SELECT (SELECT count(*) FROM matched) AS total,
           coalesce((SELECT jsonb_agg(to_jsonb(m) ORDER BY m.updated_at DESC,m.id)
                     FROM (SELECT * FROM matched ORDER BY updated_at DESC,id
                           LIMIT :limit OFFSET :offset) m),'[]'::jsonb) AS items
    """
    return {**dict(db.execute(text(query),params).mappings().one()),"limit":body.limit,"offset":body.offset}

class SaveStatisticsScope(BaseModel):
    name:str=Field(min_length=1,max_length=80)
    scope:StatisticsRequest

def scope_key(user):
    return "source.statistics.scopes."+str(user.id)

def saved_scopes(db,user):
    row=db.get(Setting,scope_key(user))
    return json.loads(row.value) if row else []

def store_scopes(db,user,items):
    key=scope_key(user)
    row=db.get(Setting,key)
    if row is None:
        row=Setting(key=key,value="[]");db.add(row)
    row.value=json.dumps(items,ensure_ascii=False)
    db.commit()

@router.get("/statistics/scopes")
def list_scopes(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return {"items":saved_scopes(db,user)}

@router.post("/statistics/scopes",dependencies=[Depends(require_origin)])
def save_scope(body:SaveStatisticsScope,db:Session=Depends(get_db),user:User=Depends(current_user)):
    name=body.name.strip()
    if not name:raise HTTPException(422,"请输入统计方案名称")
    statistics_scope(body.scope)
    admin_lock(db,user)
    items=saved_scopes(db,user)
    if len(items)>=50:raise HTTPException(422,"最多保存50个方案")
    if any(i["name"]==name for i in items):raise HTTPException(409,"已有同名方案，请更换名称")
    item={"id":str(uuid4()),"name":name,"scope":body.scope.model_dump(exclude={"limit","offset"}),"created_at":now()}
    store_scopes(db,user,[item,*items])
    return item

@router.delete("/statistics/scopes/{id}",dependencies=[Depends(require_origin)])
def delete_scope(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user)
    items=saved_scopes(db,user)
    remaining=[i for i in items if i["id"]!=id]
    if len(remaining)==len(items):raise HTTPException(404,"统计方案不存在")
    store_scopes(db,user,remaining)
    return {"items":remaining}


class StatisticsReport(StatisticsRequest):
    dimension:Literal["year","institution","exam_type"]="year"
    knowledge_name:str=Field(default="",max_length=180)
    knowledge_subject:str=Field(default="",max_length=40)

def report_data(body,db,export=False):
    cte,params=statistics_scope(body)
    dim={"year":"cohort_year","institution":"institution","exam_type":"exam_type"}[body.dimension]
    params.update(knowledge_name=body.knowledge_name.strip(),knowledge_subject=body.knowledge_subject)
    if export:params.update(limit=5000,offset=0)
    # Empty metadata has its own bucket. Include sources without any recorded questions.
    query=cte+"""
    , source_groups AS (
        SELECT id,coalesce(nullif(btrim("""+dim+"""),''),'') AS group_name,intake_status FROM selected
    ), source_totals AS (
        SELECT group_name,count(*) AS source_count,
               count(*) FILTER (WHERE intake_status='completed') AS confirmed_complete_sources
        FROM source_groups GROUP BY group_name
    ), group_pairs AS (
        SELECT DISTINCT s.group_name,p.question_id,p.source_id
        FROM pairs p JOIN source_groups s ON s.id=p.source_id
    ), question_totals AS (
        SELECT group_name,count(DISTINCT question_id) AS question_count,count(*) AS source_question_count
        FROM group_pairs GROUP BY group_name
    ), tagged AS (
        SELECT p.group_name,
               count(DISTINCT n.question_id) AS questions_with_knowledge,
               count(DISTINCT (n.subject,n.name)) AS knowledge_count,
               count(DISTINCT n.question_id) FILTER (WHERE n.name=:knowledge_name AND n.subject=:knowledge_subject) AS topic_question_count,
               count(DISTINCT (n.question_id,p.source_id)) FILTER (WHERE n.name=:knowledge_name AND n.subject=:knowledge_subject) AS topic_source_question_count
        FROM group_pairs p JOIN names n ON n.question_id=p.question_id GROUP BY p.group_name
    ), report AS (
        SELECT s.group_name,s.source_count,s.confirmed_complete_sources,
               coalesce(q.question_count,0) AS question_count,
               coalesce(q.source_question_count,0) AS source_question_count,
               coalesce(t.questions_with_knowledge,0) AS questions_with_knowledge,
               coalesce(t.knowledge_count,0) AS knowledge_count,
               coalesce(t.topic_question_count,0) AS topic_question_count,
               coalesce(t.topic_source_question_count,0) AS topic_source_question_count
        FROM source_totals s LEFT JOIN question_totals q USING(group_name)
        LEFT JOIN tagged t USING(group_name)
    )
    SELECT (SELECT count(*) FROM report) AS total,
           coalesce((SELECT jsonb_agg(to_jsonb(r) ORDER BY (r.group_name=''),r.group_name)
                     FROM (SELECT * FROM report ORDER BY (group_name=''),group_name
                           LIMIT :limit OFFSET :offset) r),'[]'::jsonb) AS items
    """
    result=dict(db.execute(text(query),params).mappings().one())
    return {**result,"dimension":body.dimension,"knowledge_name":body.knowledge_name.strip(),
            "knowledge_subject":body.knowledge_subject,"offset":params["offset"],"limit":params["limit"],
            "scope":"recorded_questions_only","original_question_total":None}

@router.post("/statistics/report",dependencies=[Depends(require_origin)])
def statistics_report(body:StatisticsReport,db:Session=Depends(get_db)):
    return report_data(body,db)

def csv_cell(value):
    # Prevent spreadsheet formula execution when a user-defined label starts with a formula prefix.
    if isinstance(value,str) and value.lstrip().startswith(("=","+","-","@")):return "'"+value
    return value

@router.post("/statistics/report/export",dependencies=[Depends(require_origin)])
def statistics_export(body:StatisticsReport,db:Session=Depends(get_db)):
    data=report_data(body,db,export=True)
    if data["total"]>5000:raise HTTPException(422,"统计分组超过5000，请缩小范围后导出")
    out=io.StringIO(newline="")
    writer=csv.writer(out)
    writer.writerow(["统计口径","仅已入库题目；零记录不等于未考查；原件总题数未知"])
    writer.writerow(["统计维度",{"year":"年份","institution":"院校或机构","exam_type":"考试类型"}[body.dimension]])
    writer.writerow(["统计范围",csv_cell(json.dumps(body.model_dump(exclude={"limit","offset"}),ensure_ascii=False))])
    writer.writerow(["分组","来源数","人工确认完成的来源","独立题目数","题目来源关联数","有知识点的题目数","知识点数","指定知识点题目数","指定知识点来源关联数"])
    for r in data["items"]:
        writer.writerow([csv_cell(r["group_name"] or "未确认"),r["source_count"],r["confirmed_complete_sources"],
                         r["question_count"],r["source_question_count"],r["questions_with_knowledge"],r["knowledge_count"],
                         r["topic_question_count"] if body.knowledge_name.strip() else "",
                         r["topic_source_question_count"] if body.knowledge_name.strip() else ""])
    return Response(content=("\ufeff"+out.getvalue()).encode("utf-8"),media_type="text/csv",
                    headers={"Content-Disposition":"attachment; filename=knowledge-statistics.csv","Cache-Control":"no-store"})


def compact_ranges(values):
    ranges=[]
    for n in sorted(values):
        if ranges and n==ranges[-1][1]+1:
            ranges[-1][1]=n
        else:ranges.append([n,n])
    return ranges

@router.get("/sources/{id}/file-progress")
def file_progress(id:str,db:Session=Depends(get_db)):
    """Only count work batches with explicit evidence of association to this source."""
    from app.models import WorkBatch,WorkMaterial,StoredFile,IntakeJob,TeachingDocument
    from app.api.workspaces import batch_states
    source(db,id)
    jobs=select(IntakeJob.id,IntakeJob.provenance).outerjoin(
        TeachingDocument,TeachingDocument.id==IntakeJob.document_id
    ).where(or_(IntakeJob.source_id==id,TeachingDocument.source_id==id))
    job_ids=set()
    batch_ids=set()
    for jid,provenance in db.execute(jobs):
        job_ids.add(jid)
        if isinstance(provenance,dict) and isinstance(provenance.get("work_batch_id"),str):
            batch_ids.add(provenance["work_batch_id"])
    if not job_ids:return {"items":[],"original_question_total":None}
    rows=list(db.execute(select(WorkBatch,WorkMaterial,StoredFile).join(
        WorkMaterial,WorkMaterial.id==WorkBatch.material_id
    ).join(StoredFile,StoredFile.id==WorkMaterial.file_id).where(
        or_(WorkBatch.job_id.in_(job_ids),WorkBatch.id.in_(batch_ids))
    ).order_by(StoredFile.name,StoredFile.id,WorkBatch.start,WorkBatch.id)))
    latest,registered=batch_states(db,[b for b,_,_ in rows])
    latest_ids={j.id for j in latest.values() if j}
    ownership={}
    if latest_ids:
        for jid,source_id,doc_id,doc_source in db.execute(select(
            IntakeJob.id,IntakeJob.source_id,IntakeJob.document_id,TeachingDocument.source_id
        ).outerjoin(TeachingDocument,TeachingDocument.id==IntakeJob.document_id).where(IntakeJob.id.in_(latest_ids))):
            ownership[jid]=doc_source if doc_id else source_id
    grouped={}
    for b,m,f in rows:
        j=latest.get(b.id)
        if not j or ownership.get(j.id)!=id:continue
        row=grouped.setdefault(f.id,{"file_id":f.id,"name":f.name,"media_type":f.media_type,
              "archived":f.archived,"purged":f.purged_at is not None,"totals":set(),
              "recognized":set(),"verified":set(),"registered":set(),"batches":0})
        if m.total_units is not None:row["totals"].add(m.total_units)
        row["recognized"].update(u["unit"] for u in b.units if u.get("state")=="done" and isinstance(u.get("unit"),int) and b.start<=u["unit"]<=b.end)
        if b.verified_text is not None:row["verified"].update(range(b.start,b.end+1))
        if b.id in registered:row["registered"].update(range(b.start,b.end+1))
        row["batches"]+=1
    items=[]
    for row in grouped.values():
        totals=row.pop("totals")
        total=next(iter(totals)) if len(totals)==1 else None
        row["total_units"]=total
        for key in ("recognized","verified","registered"):
            units=row.pop(key)
            if total is not None:units={n for n in units if 1<=n<=total}
            row[key+"_units"]=len(units)
            row[key+"_ranges"]=compact_ranges(units)
            if key=="verified":
                row["unverified_ranges"]=compact_ranges(set(range(1,total+1))-units) if total is not None and 0<total<=10000 else None
        items.append(row)
    return {"items":items,"original_question_total":None}
