"""Typed private studio records and immutable revisions. No external publication or credential handling."""
from uuid import uuid4
from typing import Literal
from urllib.parse import urlsplit
from datetime import date
from pydantic import BaseModel,Field,ValidationError
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select,func,or_
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user,require_origin,now,audit
from app.models import StudioItem as Item,StudioRevision as Version,StoredFile,TeachingDocument,TeachingResource,User
from app.services import storage
from app.api.resources import admin_lock

router=APIRouter(prefix="/studio",dependencies=[Depends(current_user)])
Kind=Literal["asset","work","publication","account","checkin"]
Platform=Literal["bilibili","douyin","xiaohongshu","wechat_top","wechat_sub"]
# Legacy template presets, not a claim of current platform limits.
PRESETS={"bilibili":[1920,1200,5,5,4,4],"douyin":[1080,1920,13,21,4,16.5],"xiaohongshu":[1242,1660,6,12,5,12],"wechat_top":[900,383,6,30,28.7,28.7],"wechat_sub":[500,500,8,8,8,8]}
class Asset(BaseModel):
    category:Literal["image","template","formula"]
    file_id:str|None=Field(default=None,max_length=36)
    content:str=Field(default="",max_length=20000)
    tags:list[str]=Field(default_factory=list,max_length=20)
    note:str=Field(default="",max_length=2000)
    favorite:bool=False
class Work(BaseModel):
    category:Literal["drawing","cover","article","slides","document"]
    file_id:str|None=Field(default=None,max_length=36)
    document_id:str|None=Field(default=None,max_length=36)
    resource_id:str|None=Field(default=None,max_length=36)
    content:str=Field(default="",max_length=50000)
    note:str=Field(default="",max_length=2000)
class Publication(BaseModel):
    platform:Platform
    work_id:str=Field(max_length=36)
    caption:str=Field(default="",max_length=20000)
    tags:str=Field(default="",max_length=400)
    state:Literal["draft","ready","published"]="draft"
    url:str=Field(default="",max_length=2048)
    views:int|None=Field(default=None,ge=0,le=1000000000)
    likes:int|None=Field(default=None,ge=0,le=1000000000)
    comments:int|None=Field(default=None,ge=0,le=1000000000)
    observed_on:date|None=None
class Account(BaseModel):
    platform:Literal["qoder_cn","qoder_global","codebuddy"]
    note:str=Field(default="",max_length=2000)
class Checkin(BaseModel):
    account_id:str=Field(max_length=36)
    day:date
    state:Literal["success","failed","skipped"]
    earned:float|None=Field(default=None,ge=0,le=100000000)
    balance:float|None=Field(default=None,ge=0,le=100000000)
    note:str=Field(default="",max_length=2000)
class Draft(BaseModel):
    kind:Kind
    title:str=Field(min_length=1,max_length=200)
    data:dict
    revision:int|None=Field(default=None,ge=1)
SCHEMAS={"asset":Asset,"work":Work,"publication":Publication,"account":Account,"checkin":Checkin}
def public(r):
    return {k:getattr(r,k) for k in ("id","kind","title","data","revision","archived","created_at","updated_at")}
def existing(db,id,kind=None):
    r=db.get(Item,id)
    if not r or (kind and r.kind!=kind):raise HTTPException(404,"记录不存在")
    return r
def validate(db,body,ident=None):
    if not body.title.strip():raise HTTPException(422,"标题不能为空")
    try:d=SCHEMAS[body.kind].model_validate(body.data).model_dump(mode="json")
    except ValidationError:raise HTTPException(422,"记录字段格式或长度错误")
    file_id=d.get("file_id")
    if file_id:
        f=db.scalar(select(StoredFile).where(StoredFile.id==file_id).with_for_update())
        if not f or f.archived:raise HTTPException(422,"文件不存在或已归档")
        if body.kind=="asset" and d["category"]=="image" and f.media_type not in storage.IMAGE_TYPES:raise HTTPException(422,"请选择图片文件")
    if body.kind=="asset":
        if d["category"]=="image" and not file_id:raise HTTPException(422,"图片素材需要文件")
        if d["category"]=="formula" and not d["content"].strip():raise HTTPException(422,"公式不能为空")
        if d["category"]=="template" and not (file_id or d["content"].strip()):raise HTTPException(422,"模板需要文件或正文")
        if any(len(t)>60 for t in d["tags"]):raise HTTPException(422,"标签过长")
        d["tags"]=list(dict.fromkeys(t.strip() for t in d["tags"] if t.strip()))
    if body.kind=="work":
        for key,cls in (("document_id",TeachingDocument),("resource_id",TeachingResource)):
            if d[key]:
                r=db.get(cls,d[key])
                if not r or r.archived:raise HTTPException(422,"关联资源无效")
        if not (file_id or d["document_id"] or d["resource_id"] or d["content"].strip()):raise HTTPException(422,"作品需要内容或关联文件")
    if body.kind=="publication":
        w=existing(db,d["work_id"],"work")
        if w.archived:raise HTTPException(422,"作品已归档")
        if d["url"]:
            try:u=urlsplit(d["url"]); valid=u.scheme=="https" and bool(u.hostname) and not u.username and not u.password
            except ValueError:valid=False
            if not valid:raise HTTPException(422,"请输入有效HTTPS发布链接")
        if d["state"]=="published" and not d["url"]:raise HTTPException(422,"已发布状态需要真实链接")
        if any(d[k] is not None for k in ("views","likes","comments")) and not d["observed_on"]:raise HTTPException(422,"运营数据需记录观察日期")
    if body.kind=="checkin":
        a=existing(db,d["account_id"],"account")
        if a.archived:raise HTTPException(422,"账户已归档")
        rows=db.scalars(select(Item).where(Item.kind=="checkin",Item.archived==False))
        if any(r.id!=ident and r.data.get("account_id")==a.id and r.data.get("day")==d["day"] for r in rows):raise HTTPException(409,"该账户当天已有记录")
    return d
def save_version(db,r):
    db.add(Version(item_id=r.id,revision=r.revision,snapshot=public(r),created_at=now()))
    # Keep file references for all historical revisions, even when the current file changes.
    if r.data.get("file_id"):storage.link_file(db,r.data["file_id"],"studio_item",r.id)
@router.get("/presets")
def presets():return PRESETS
@router.get("")
def listing(kind:Kind,q:str=Query("",max_length=200),category:str=Query("",max_length=24),favorite:bool=False,archived:bool=False,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    stmt=select(Item).where(Item.kind==kind,Item.archived==archived)
    if category:stmt=stmt.where(Item.data["category"].as_string()==category)
    if favorite:stmt=stmt.where(Item.data["favorite"].as_boolean()==True)
    if q.strip():stmt=stmt.where(or_(Item.title.contains(q.strip(),autoescape=True),Item.data["note"].as_string().contains(q.strip(),autoescape=True),Item.data["content"].as_string().contains(q.strip(),autoescape=True)))
    return {"items":[public(r) for r in db.scalars(stmt.order_by(Item.updated_at.desc(),Item.id).offset(offset).limit(limit))],"total":db.scalar(select(func.count()).select_from(stmt.subquery()))}
@router.post("",dependencies=[Depends(require_origin)])
def create(body:Draft,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);d=validate(db,body)
    r=Item(id=str(uuid4()),kind=body.kind,title=body.title.strip(),data=d,revision=1,archived=False,created_at=now(),updated_at=now())
    db.add(r);db.flush();save_version(db,r);audit(db,"studio.create",user.id);db.commit();return public(r)
@router.put("/{id}",dependencies=[Depends(require_origin)])
def update(id:str,body:Draft,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);r=existing(db,id)
    if r.archived or r.kind!=body.kind or r.revision!=body.revision:raise HTTPException(409,"记录版本冲突")
    r.data=validate(db,body,id);r.title=body.title.strip();r.revision+=1;r.updated_at=now()
    save_version(db,r);audit(db,"studio.update",user.id);db.commit();return public(r)
@router.get("/{id}/versions")
def versions(id:str,db:Session=Depends(get_db)):
    existing(db,id)
    return [v.snapshot for v in db.scalars(select(Version).where(Version.item_id==id).order_by(Version.revision.desc()).limit(100))]
@router.post("/{id}/archive",dependencies=[Depends(require_origin)])
def archive(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);r=existing(db,id)
    dependent={"work":("publication","work_id"),"account":("checkin","account_id")}.get(r.kind)
    if dependent and any(x.data.get(dependent[1])==r.id for x in db.scalars(select(Item).where(Item.kind==dependent[0],Item.archived==False))):raise HTTPException(409,"仍有有效关联记录")
    if not r.archived:r.archived=True;r.revision+=1;r.updated_at=now();save_version(db,r);audit(db,"studio.archive",user.id);db.commit()
    return public(r)
@router.post("/{id}/restore",dependencies=[Depends(require_origin)])
def restore(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);r=existing(db,id)
    if r.archived:
        validate(db,Draft(kind=r.kind,title=r.title,data=r.data),r.id)
        r.archived=False;r.revision+=1;r.updated_at=now();save_version(db,r);audit(db,"studio.restore",user.id);db.commit()
    return public(r)
