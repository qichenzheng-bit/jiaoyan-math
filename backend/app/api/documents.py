"""Persistent Word-like block drafts. No browser-supplied snapshots or filesystem paths."""
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, now, audit
from app.core.solution_methods import normalize_subject
from app.models import TeachingDocument as Doc, DocumentResourceReference as Ref, TeachingResource as Resource, StoredFile, FileReference, User
from app.services import storage
from app.api import resources as bank

router=APIRouter(prefix="/documents",tags=["documents"],dependencies=[Depends(current_user)])
class Block(BaseModel):
    uid:str=Field(min_length=1,max_length=36,pattern=r"^[A-Za-z0-9_-]+$")
    kind:Literal["heading","text","question","knowledge","reference","image","pagebreak"]
    title:str=Field(default="",max_length=200)
    content:str=Field(default="",max_length=50000)
    answer:str=Field(default="",max_length=20000)
    solution:str=Field(default="",max_length=50000)
    analysis:str=Field(default="",max_length=50000)
    proof:str=Field(default="",max_length=50000)
    chapter:str=Field(default="",max_length=120)
    question_type:str=Field(default="",max_length=20)
    unit_type:str=Field(default="",max_length=24)
    resource_id:str|None=Field(default=None,max_length=36)
    file_id:str|None=Field(default=None,max_length=36)
    width:int=Field(default=100,ge=20,le=100)
    score:float=Field(default=0,ge=0,le=1000)
class Draft(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    kind:Literal["intake","handout","paper"]="intake"
    subject:str=Field(default="",max_length=40)
    source_id:str|None=Field(default=None,max_length=36)
    blocks:list[Block]=Field(default_factory=list,max_length=200)
    revision:int|None=Field(default=None,ge=1)
class Register(BaseModel):
    revision:int=Field(ge=1)
    duplicate_reason:str=Field(default="",max_length=200)
    bind_source:bool=False
def row(db,id):
    d=db.scalar(select(Doc).where(Doc.id==id).with_for_update())
    if not d:raise HTTPException(404,"文档不存在")
    return d
def summary(d):return {k:getattr(d,k) for k in ("id","title","kind","subject","source_id","revision","archived","created_at","updated_at")}
def public(d):return {**summary(d),"blocks":d.blocks}
def validate(db,body,previous):
    if not body.title.strip():raise HTTPException(422,"文档标题不能为空")
    if body.source_id:
        src=db.get(Resource,body.source_id)
        if not src or src.kind!="source" or src.archived:raise HTTPException(422,"来源资料无效")
    if len({b.uid for b in body.blocks})!=len(body.blocks):raise HTTPException(422,"文档块编号重复")
    total=sum(len(b.content)+len(b.solution)+len(b.answer)+len(b.proof)+len(b.analysis) for b in body.blocks)
    if total>500000:raise HTTPException(422,"文档过长，请拆分")
    old={b["uid"]:b for b in previous}
    result=[]
    for b in body.blocks:
        data=b.model_dump()
        if b.kind=="reference":
            prior=old.get(b.uid,{})
            if prior.get("kind")=="reference" and prior.get("resource_id")==b.resource_id and prior.get("snapshot"):
                data["snapshot"]=prior["snapshot"]
            else:
                r=db.get(Resource,b.resource_id) if b.resource_id else None
                if not r or r.archived or r.kind not in ("question","knowledge"):raise HTTPException(422,"引用资源无效")
                data["snapshot"]=bank.view(r)
        elif b.resource_id:raise HTTPException(422,"仅引用块可以绑定题库资源")
        if b.kind=="image":
            f=db.get(StoredFile,b.file_id) if b.file_id else None
            if not f or f.archived or f.media_type not in storage.IMAGE_TYPES:raise HTTPException(422,"图片无效")
        elif b.file_id:raise HTTPException(422,"仅图片块允许文件引用")
        result.append(data)
    if sum(len(str(b.get("snapshot",""))) for b in result)>1_000_000:raise HTTPException(422,"引用内容过多，请拆分文档")
    return result
def references(db,d):
    wanted={b["resource_id"] for b in d.blocks if b["kind"]=="reference"}
    if d.source_id:wanted.add(d.source_id)
    old=set(db.scalars(select(Ref.resource_id).where(Ref.document_id==d.id)))
    for id in old-wanted:db.delete(db.get(Ref,(d.id,id)))
    for id in wanted-old:db.add(Ref(document_id=d.id,resource_id=id))
    files={b["file_id"] for b in d.blocks if b["kind"]=="image"}
    existing=set(db.scalars(select(FileReference.file_id).where(FileReference.owner_type=="teaching_document",FileReference.owner_id==d.id)))
    for id in existing-files:db.delete(db.get(FileReference,(id,"teaching_document",d.id)))
    for id in files-existing:storage.link_file(db,id,"teaching_document",d.id)
@router.get("")
def listing(q:str=Query("",max_length=200),archived:bool=False,kind:Literal["intake","handout","paper"]|None=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    stmt=select(Doc).where(Doc.archived==archived)
    if q.strip():stmt=stmt.where(Doc.title.contains(q.strip(),autoescape=True))
    if kind:stmt=stmt.where(Doc.kind==kind)
    return {"items":[summary(d) for d in db.scalars(stmt.order_by(Doc.updated_at.desc(),Doc.id).offset(offset).limit(limit))],"total":db.scalar(select(func.count()).select_from(stmt.subquery()))}
@router.post("",dependencies=[Depends(require_origin)])
def create(body:Draft,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user)
    d=Doc(id=str(uuid4()),title=body.title.strip(),kind=body.kind,subject=normalize_subject(body.subject),source_id=body.source_id,blocks=validate(db,body,[]),revision=1,archived=False,created_at=now(),updated_at=now())
    db.add(d);db.flush();references(db,d);audit(db,"document.create",user.id);db.commit();return public(d)
@router.get("/{id}")
def read(id:str,db:Session=Depends(get_db)):return public(row(db,id))
@router.put("/{id}",dependencies=[Depends(require_origin)])
def update(id:str,body:Draft,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);d=row(db,id)
    if d.archived or d.revision!=body.revision:raise HTTPException(409,"文档版本冲突或已归档，请重新加载")
    d.blocks=validate(db,body,d.blocks);d.title=body.title.strip();d.subject=normalize_subject(body.subject);d.source_id=body.source_id;d.kind=body.kind
    d.revision+=1;d.updated_at=now();references(db,d);audit(db,"document.update",user.id);db.commit();return public(d)
@router.post("/{id}/archive",dependencies=[Depends(require_origin)])
def archive(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);d=row(db,id);d.archived=True;d.revision+=1;d.updated_at=now();audit(db,"document.archive",user.id);db.commit();return public(d)
@router.post("/{id}/restore",dependencies=[Depends(require_origin)])
def restore(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);d=row(db,id);d.archived=False;d.revision+=1;d.updated_at=now();audit(db,"document.restore",user.id);db.commit();return public(d)

@router.post("/{id}/blocks/{uid}/register",dependencies=[Depends(require_origin)])
def register(id:str,uid:str,body:Register,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);d=row(db,id)
    if d.archived or d.revision!=body.revision:raise HTTPException(409,"文档版本冲突")
    block=next((b for b in d.blocks if b["uid"]==uid),None)
    if not block:raise HTTPException(404,"文档块不存在")
    if block["kind"]=="reference":return public(d)
    if block["kind"] not in ("question","knowledge") or not block["title"].strip() or not block["content"].strip():raise HTTPException(422,"只能将完整题目或知识单元入库")
    draft=bank.Draft(kind=block["kind"],title=block["title"],subject=d.subject,content=block["content"],answer=block["answer"],solution=block["solution"],analysis=block["analysis"],proof=block["proof"],chapter=block["chapter"],question_type=block["question_type"],unit_type=block["unit_type"],source_id=d.source_id if body.bind_source else None,dedup_override=bool(body.duplicate_reason.strip()),dedup_reason=body.duplicate_reason)
    values=bank.clean(draft,db);bank.guard_duplicate(db,values)
    primary=values.pop("source_id")
    r=Resource(id=str(uuid4()),code=bank.new_code(db,draft.kind),**values,source_id=None,revision=1,sources_revision=1,archived=False,created_at=now(),updated_at=now())
    db.add(r);db.flush()
    if primary:bank.change_primary(db,r,primary)
    replacement=Block(uid=uid,kind="reference",resource_id=r.id,score=block.get("score",0)).model_dump()
    replacement["snapshot"]=bank.view(r)
    d.blocks=[replacement if b["uid"]==uid else b for b in d.blocks]
    d.revision+=1;d.updated_at=now();references(db,d);audit(db,"resource.create",user.id);audit(db,"document.register",user.id);db.commit();return public(d)

@router.post("/{id}/promote",dependencies=[Depends(require_origin)])
def promote(id:str,body:Register,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);d=row(db,id)
    if d.archived or d.revision!=body.revision or d.kind not in ("paper","handout") or not d.blocks:raise HTTPException(409,"文档不可转正或版本冲突")
    if d.source_id:return public(d)
    text="自编"+("试卷" if d.kind=="paper" else "讲义")+"；对应文档编号 "+d.id
    data=bank.clean(bank.Draft(kind="source",title=d.title,subject=d.subject,content=text,source_type="exam" if d.kind=="paper" else "handout",authority_tier="internal_handout"),db)
    r=Resource(id=str(uuid4()),code=bank.new_code(db,"source"),**data,revision=1,sources_revision=1,archived=False,created_at=now(),updated_at=now())
    db.add(r);db.flush();bank.snapshot(db,r)
    d.source_id=r.id;d.revision+=1;d.updated_at=now();references(db,d)
    audit(db,"document.promote",user.id);db.commit();return public(d)
