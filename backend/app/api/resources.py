from typing import Literal
from uuid import uuid4
from difflib import SequenceMatcher
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, delete
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, audit, now
from app.core.solution_methods import normalize_subject, MATH_SUBJECTS, parse_methods, recommended_solution
from app.core.content_normalization import question_fingerprint, unit_fingerprint, canonical_text, question_stem_key
from app.models import TeachingResource, User, ResourceSourceLink, SourceVersion, StoredFile, FileReference, DocumentResourceReference, IntakeJob
from app.services import storage

router=APIRouter(prefix="/resources",tags=["resources"],dependencies=[Depends(current_user)])
Kind=Literal["question","knowledge","source"]
SOURCE_TYPES=["textbook","exam","handout","other"]
AUTHORITY_TIERS=["","official_exam","core_textbook","internal_handout","mock_practice"]
class Draft(BaseModel):
    kind:Kind
    title:str=Field(min_length=1,max_length=200)
    subject:str=Field(default="",max_length=40)
    content:str=Field(min_length=1,max_length=50000)
    answer:str=Field(default="",max_length=20000)
    solution:str=Field(default="",max_length=50000)
    tags:list[str]=Field(default_factory=list,max_length=20)
    source_id:str|None=Field(default=None,max_length=36)
    exam_type:str=Field(default="",max_length=80)
    chapter:str=Field(default="",max_length=120)
    question_type:str=Field(default="",max_length=20)
    difficulty:Literal["","简单","中等","困难"]|None=None
    unit_type:str=Field(default="",max_length=24)
    analysis:str=Field(default="",max_length=50000)
    proof:str=Field(default="",max_length=50000)
    exams:list[str]=Field(default_factory=list,max_length=20)
    source_type:str=Field(default="",max_length=16)
    authority_tier:str=Field(default="",max_length=24)
    cohort_year:str=Field(default="",max_length=12)
    series_key:str=Field(default="",max_length=80)
    edition:str=Field(default="",max_length=60)
    revision:int|None=Field(default=None,ge=1)
    dedup_override:bool=False
    dedup_reason:str=Field(default="",max_length=200)

def clean(body,db):
    d=body.model_dump(exclude={"revision"})
    d["difficulty"]=body.difficulty or ""
    for key in ("title","content"):
        if not d[key].strip(): raise HTTPException(422,"标题和内容不能为空")
    d["title"]=d["title"].strip()
    d["subject"]=normalize_subject(d["subject"])
    for field in ("tags","exams"):
        if any(len(t)>60 for t in d[field]): raise HTTPException(422,"标签或考试类别最多60字")
        d[field]=list(dict.fromkeys(t.strip() for t in d[field] if t.strip()))
    if body.kind!="question":
        for key in ("answer","solution","analysis","question_type","difficulty"): d[key]=""
    if body.kind!="knowledge":
        d.update(unit_type="",proof="",exams=[])
    if body.kind=="source":
        if body.source_id: raise HTTPException(422,"来源资料不能关联自身来源")
        d["source_type"]=body.source_type or "other"
        if d["source_type"] not in SOURCE_TYPES or d["authority_tier"] not in AUTHORITY_TIERS: raise HTTPException(422,"来源分类无效")
    else:
        for key in ("source_type","authority_tier","cohort_year","series_key","edition"): d[key]=""
    if body.source_id:
        src=db.get(TeachingResource,body.source_id)
        if not src or src.kind!="source" or src.archived: raise HTTPException(422,"来源资料不存在或已归档")
    d["fingerprint"]=question_fingerprint(d["content"],d["solution"],d["answer"]) if body.kind=="question" else unit_fingerprint(d["title"],d["content"])
    d["stem_key"]=question_stem_key(d["content"]) if body.kind=="question" else ""
    d["dedup_reason"]=d["dedup_reason"].strip() if d["dedup_override"] else ""
    return d

FIELDS=("id","code","kind","title","subject","content","answer","solution","tags","source_id","archived","created_at","updated_at","revision","sources_revision","exam_type","chapter","question_type","difficulty","unit_type","analysis","proof","exams","source_type","authority_tier","cohort_year","series_key","edition","dedup_override","dedup_reason")
def view(row): return {k:getattr(row,k) for k in FIELDS}
def existing(db,ident,lock=False):
    stmt=select(TeachingResource).where(TeachingResource.id==ident)
    row=db.scalar(stmt.with_for_update() if lock else stmt)
    if not row: raise HTTPException(404,"资源不存在")
    return row
def admin_lock(db,user):
    db.scalar(select(User).where(User.id==user.id).with_for_update())
def new_code(db,kind):
    while True:
        code={"question":"Q","knowledge":"K","source":"S"}[kind]+uuid4().hex[:8].upper()
        if not db.scalar(select(TeachingResource.id).where(TeachingResource.code==code)): return code
def exact(db,d,exclude=None):
    stmt=select(TeachingResource).where(TeachingResource.kind==d["kind"],TeachingResource.fingerprint==d["fingerprint"])
    if exclude: stmt=stmt.where(TeachingResource.id!=exclude)
    return stmt
def source_identity_matches(db,data,exclude=None):
    """Source identity is independent of notes and extracted text. Unknown metadata is not evidence of a distinct edition."""
    if data["kind"]!="source":return []
    stmt=select(TeachingResource).where(TeachingResource.kind=="source",TeachingResource.source_type==data["source_type"])
    if exclude:stmt=stmt.where(TeachingResource.id!=exclude)
    def compatible(a,b):
        a,b=canonical_text(a),canonical_text(b)
        return not a or not b or a==b
    return [r for r in db.scalars(stmt) if canonical_text(r.title)==canonical_text(data["title"])
            and all(compatible(getattr(r,k),data[k]) for k in ("cohort_year","exam_type","edition","series_key"))][:20]

def guard_source_identity(db,data,exclude=None):
    if source_identity_matches(db,data,exclude):
        raise HTTPException(409,"存在同名且资料信息相符的来源（含归档资料），请先复用或核对年份、考试类别、版次。备注不同不能作为新建依据。")

def active_source(db,ident,lock=False):
    src=existing(db,ident,lock)
    if src.kind!="source" or src.archived:raise HTTPException(422,"请选择未归档的来源资料")
    return src

def guard_duplicate(db,d,exclude=None):
    if db.scalar(exact(db,d,exclude).limit(1)):
        if not d["dedup_override"] or not d["dedup_reason"]:
            raise HTTPException(409,"发现完全重复资源；请确认保留并填写原因")
def links(db,row):
    return list(db.scalars(select(ResourceSourceLink).where(ResourceSourceLink.resource_id==row.id)))
def change_primary(db,row,source_id):
    if row.source_id==source_id and links(db,row): return
    old=links(db,row)
    for link in old: link.is_primary=False
    if source_id:
        target=next((l for l in old if l.source_id==source_id),None)
        if target: target.is_primary=True
        else: db.add(ResourceSourceLink(resource_id=row.id,source_id=source_id,provenance_role="original",original_question_number="",chapter="",note="",is_primary=True,role_verified=False,page_start=None,page_end=None))
    row.source_id=source_id
    if old or source_id: row.sources_revision+=1
def snapshot(db,row):
    if row.kind=="source":
        db.add(SourceVersion(source_id=row.id,version=row.revision,snapshot=view(row),created_at=now()))

@router.get("/subjects")
def subjects(): return list(MATH_SUBJECTS)

@router.get("")
def listing(kind:Kind|None=None,subject:str="",q:str=Query("",max_length=200),chapter:str=Query("",max_length=120),question_type:str=Query("",max_length=20),unit_type:str=Query("",max_length=24),exam_type:str=Query("",max_length=80),source_type:str=Query("",max_length=16),authority_tier:str=Query("",max_length=24),archived:bool=False,limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    filters=[TeachingResource.archived==archived]
    if kind: filters.append(TeachingResource.kind==kind)
    if subject: filters.append(TeachingResource.subject==normalize_subject(subject))
    for key,value in (("chapter",chapter),("question_type",question_type),("unit_type",unit_type),("exam_type",exam_type),("source_type",source_type),("authority_tier",authority_tier)):
        if key=="question_type" and value=="综合题":
            filters.append(TeachingResource.question_type.in_(("综合题","解答题","计算题","证明题")))
        elif value: filters.append(getattr(TeachingResource,key)==value)
    if q.strip():
        term=q.strip()
        filters.append(or_(TeachingResource.title.contains(term,autoescape=True),TeachingResource.content.contains(term,autoescape=True),TeachingResource.code.ilike(term.upper().replace("%","\\%").replace("_","\\_"),escape="\\") if term.isalnum() else TeachingResource.code==term.upper()))
    total=db.scalar(select(func.count()).select_from(TeachingResource).where(*filters))
    rows=db.scalars(select(TeachingResource).where(*filters).order_by(TeachingResource.updated_at.desc(),TeachingResource.id).offset(offset).limit(limit))
    return {"items":[view(r) for r in rows],"total":total}

@router.post("/source-matches",dependencies=[Depends(require_origin)])
def source_matches(body:Draft,db:Session=Depends(get_db)):
    return [view(r) for r in source_identity_matches(db,clean(body,db))]

@router.post("/duplicates",dependencies=[Depends(require_origin)])
def duplicates(body:Draft,db:Session=Depends(get_db)):
    return [view(r) for r in db.scalars(exact(db,clean(body,db)).limit(20))]

@router.post("/similar",dependencies=[Depends(require_origin)])
def similar(body:Draft,db:Session=Depends(get_db)):
    d=clean(body,db)
    query=canonical_text(d["content"])[:3000]
    rows=list(db.scalars(select(TeachingResource).where(TeachingResource.kind==body.kind,TeachingResource.fingerprint!=d["fingerprint"],TeachingResource.archived==False).order_by(TeachingResource.updated_at.desc(),TeachingResource.id).limit(300)))
    exact_stems=list(db.scalars(select(TeachingResource).where(TeachingResource.kind=="question",TeachingResource.stem_key==d["stem_key"],TeachingResource.fingerprint!=d["fingerprint"],TeachingResource.archived==False).order_by(TeachingResource.updated_at.desc(),TeachingResource.id).limit(10))) if body.kind=="question" else []
    items=[{"resource":view(r),"similarity":1.0,"reason":"规范化题干相同，答案或解析不同","match_kind":"same_stem"} for r in exact_stems]
    seen={r.id for r in exact_stems}
    for r in rows:
        if r.id in seen:continue
        score=SequenceMatcher(None,query,canonical_text(r.content)[:3000]).ratio()
        if score>=.75: items.append({"resource":view(r),"similarity":round(score,3),"reason":"题干或正文相似，答案、解析或标题可能不同","match_kind":"similar"})
    return {"items":sorted(items,key=lambda x:x["similarity"],reverse=True)[:10],"mode":"recent_python","scanned":len(rows),"scan_limit":300}

@router.post("",dependencies=[Depends(require_origin)])
def create(body:Draft,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user)
    d=clean(body,db)
    if body.kind=="source":guard_source_identity(db,d)
    else:guard_duplicate(db,d)
    primary=d.pop("source_id")
    row=TeachingResource(id=str(uuid4()),code=new_code(db,body.kind),**d,source_id=None,revision=1,sources_revision=1,archived=False,created_at=now(),updated_at=now())
    db.add(row);db.flush()
    if primary: change_primary(db,row,primary)
    snapshot(db,row);audit(db,"resource.create",user.id);db.commit()
    return view(row)

@router.get("/{id}")
def read(id:str,db:Session=Depends(get_db)): return view(existing(db,id))

@router.put("/{id}",dependencies=[Depends(require_origin)])
def update(id:str,body:Draft,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user)
    row=existing(db,id,True)
    if row.kind!=body.kind or row.archived: raise HTTPException(409,"不能修改资源类型或已归档资源")
    if body.revision!=row.revision: raise HTTPException(409,"资源已修改，请重新加载")
    d=clean(body,db)
    if row.kind!="source" and d["fingerprint"]!=row.fingerprint: guard_duplicate(db,d,id)
    if row.kind=="source" and any(d[k]!=getattr(row,k) for k in ("title","source_type","cohort_year","exam_type","edition","series_key")):guard_source_identity(db,d,id)
    primary=d.pop("source_id")
    if body.difficulty is None:d.pop("difficulty",None)
    for k,v in d.items(): setattr(row,k,v)
    if row.source_id!=primary: change_primary(db,row,primary)
    row.revision+=1;row.updated_at=now();snapshot(db,row);audit(db,"resource.update",user.id);db.commit()
    return view(row)

def set_archived(db,row,value,user):
    if row.archived==value: return view(row)
    if value and row.kind=="source":
        if db.scalar(select(IntakeJob.id).where(IntakeJob.source_id==row.id,IntakeJob.state.in_(("running","review"))).limit(1)):
            raise HTTPException(409,"来源仍被待处理录入任务使用，请先完成或停止任务")
        if db.scalar(select(DocumentResourceReference.document_id).where(DocumentResourceReference.resource_id==row.id).limit(1)):
            raise HTTPException(409,"来源已被文档引用，请先解除绑定")
        if db.scalar(select(ResourceSourceLink.resource_id).where(ResourceSourceLink.source_id==row.id).limit(1)):
            raise HTTPException(409,"来源仍被资源引用，请先解除关联")
    row.archived=value;row.revision+=1;row.updated_at=now();snapshot(db,row)
    audit(db,"resource.archive" if value else "resource.restore",user.id);db.commit()
    return view(row)

@router.post("/{id}/archive",dependencies=[Depends(require_origin)])
def archive(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);return set_archived(db,existing(db,id,True),True,user)
@router.post("/{id}/restore",dependencies=[Depends(require_origin)])
def restore(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);return set_archived(db,existing(db,id,True),False,user)

@router.get("/{id}/methods")
def methods(id:str,db:Session=Depends(get_db)):
    row=existing(db,id)
    return {"methods":parse_methods(row.solution),"recommended":recommended_solution(row.solution)}

class SourceLink(BaseModel):
    source_id:str=Field(max_length=36)
    provenance_role:Literal["original","reproduced","adapted"]="original"
    original_question_number:str=Field(default="",max_length=40)
    page_start:int|None=Field(default=None,ge=1)
    page_end:int|None=Field(default=None,ge=1)
    chapter:str=Field(default="",max_length=120)
    note:str=Field(default="",max_length=300)
    is_primary:bool=False
    role_verified:bool=True
class SourceLinks(BaseModel):
    revision:int=Field(ge=1)
    items:list[SourceLink]=Field(max_length=100)
def link_view(db,row):
    return {"revision":row.sources_revision,"items":[{**{k:getattr(l,k) for k in SourceLink.model_fields},"source_title":db.get(TeachingResource,l.source_id).title} for l in links(db,row)]}

@router.get("/{id}/sources")
def list_sources(id:str,db:Session=Depends(get_db)): return link_view(db,existing(db,id))
@router.put("/{id}/sources",dependencies=[Depends(require_origin)])
def replace_sources(id:str,body:SourceLinks,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);row=existing(db,id,True)
    if row.kind=="source" or row.archived: raise HTTPException(409,"当前资源不能修改来源")
    if row.sources_revision!=body.revision: raise HTTPException(409,"来源关联已修改，请重新加载")
    keys=set();primary=None
    for item in body.items:
        src=db.get(TeachingResource,item.source_id)
        key=(item.source_id,item.provenance_role)
        if not src or src.kind!="source" or src.archived or key in keys: raise HTTPException(422,"来源无效或重复")
        if item.page_start and item.page_end and item.page_end<item.page_start: raise HTTPException(422,"结束页不能小于起始页")
        if item.is_primary:
            if primary: raise HTTPException(422,"只能选择一个主要来源")
            primary=item.source_id
        keys.add(key)
    db.execute(delete(ResourceSourceLink).where(ResourceSourceLink.resource_id==row.id))
    db.flush()
    for item in body.items: db.add(ResourceSourceLink(resource_id=row.id,**item.model_dump()))
    row.source_id=primary;row.sources_revision+=1;row.revision+=1;row.updated_at=now()
    audit(db,"resource.sources.update",user.id);db.commit()
    return link_view(db,row)

@router.get("/{id}/versions")
def versions(id:str,db:Session=Depends(get_db)):
    row=existing(db,id)
    if row.kind!="source": raise HTTPException(422,"仅来源资料支持此版本接口")
    return [{"version":v.version,"snapshot":v.snapshot,"created_at":v.created_at} for v in db.scalars(select(SourceVersion).where(SourceVersion.source_id==id).order_by(SourceVersion.version.desc()).limit(100))]
