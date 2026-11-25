import json
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user,require_origin,now,audit
from app.core.solution_methods import normalize_subject
from app.models import IntakeJob as Job, TeachingDocument, StoredFile, User
from app.services.pdf_text import extract_pdf
from app.api import qoder, documents as docs, resources as bank

router=APIRouter(prefix="/intelligence",dependencies=[Depends(current_user)])
class Start(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    subject:str=Field(default="",max_length=40)
    text:str=Field(min_length=1,max_length=24000)
    model:str=Field(default="Auto",max_length=80,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
class Review(BaseModel):
    revision:int=Field(ge=1)
    items:list[docs.Block]=Field(max_length=100)
class Confirm(BaseModel):
    revision:int=Field(ge=1)
def parse_answer(text):
    text=text.strip()
    fence=chr(96)*3
    if text.startswith(fence+"json") and text.endswith(fence):text=text[7:-3].strip()
    data=json.loads(text)
    if not isinstance(data,list) or not 0<len(data)<=100:raise ValueError("invalid list")
    result=[]
    for item in data:
        if not isinstance(item,dict):raise ValueError("invalid item")
        b=docs.Block.model_validate({**item,"uid":str(uuid4()),"resource_id":None,"file_id":None})
        if b.kind not in ("question","knowledge") or not b.title.strip() or not b.content.strip():raise ValueError("invalid block")
        result.append(b.model_dump())
    return result
def view(j,full=False):
    r={k:getattr(j,k) for k in ("id","title","subject","model","state","detail","document_id","revision","created_at","updated_at")}
    if full:r.update(items=j.items,input_text=j.input_text)
    return r
def get_job(db,id):
    j=db.scalar(select(Job).where(Job.id==id).with_for_update())
    if not j:raise HTTPException(404,"任务不存在")
    return j
def sync(db,j):
    if j.state!="running":return
    try:r=qoder.request("GET","/chat/"+j.id)
    except HTTPException as e:
        if (e.status_code==404 and now()-j.created_at>15) or now()-j.created_at>300:j.state="failed";j.detail="执行任务已失效，请重新发起"
        else:return
    else:
        s=r.get("state")
        if s=="running":return
        if s=="done":
            try:j.items=parse_answer(r.get("answer",""));j.state="review";j.detail="提取结果待人工核对，未入库"
            except (ValueError,TypeError):j.state="failed";j.detail="结构化结果无效，请缩小批次后重试"
        else:j.state="stopped" if s=="stopped" else "failed";j.detail=str(r.get("detail","执行失败"))[:400]
    j.revision+=1;j.updated_at=now();db.commit()
@router.get("/jobs")
def listing(db:Session=Depends(get_db)):
    return [view(j) for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(100))]
@router.get("/jobs/{id}")
def detail(id:str,db:Session=Depends(get_db)):
    j=get_job(db,id);sync(db,j);return view(j,True)
@router.post("/jobs",dependencies=[Depends(require_origin)])
def start(body:Start,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not body.title.strip() or not body.text.strip():raise HTTPException(422,"标题和原文不能为空")
    prompt="你是数学资料录入助手。仅依据原文提取题目与知识单元，不补造答案、证明或图形。保持数学含义、LaTeX、多种解法，连续页跨页题干合并。无法确认的字段留空或在analysis标记待核对。仅输出JSON数组，每项kind(question或knowledge),title,content,answer,solution,analysis,proof,chapter,question_type,unit_type。最多100项。\n学科："+body.subject+"\n【原文】\n"+body.text+"\n【原文结束】"
    if len(prompt.encode("utf-8"))>100000:raise HTTPException(422,"原文过长")
    if not qoder.request("GET","/status").get("chat_available"):raise HTTPException(503,"独立Qoder执行服务需升级至V3")
    j=Job(id=str(uuid4()),title=body.title.strip(),subject=normalize_subject(body.subject),input_text=body.text,model=body.model,state="running",detail="",items=[],document_id=None,revision=1,created_at=now(),updated_at=now())
    db.add(j);audit(db,"intelligence.start",user.id);db.commit()
    try:qoder.request("POST","/chat/start",{"id":j.id,"model":j.model,"prompt":prompt})
    except HTTPException as e:
        j=get_job(db,j.id);j.state="failed";j.detail=str(e.detail)[:400];j.revision+=1;db.commit()
    return view(j,True)
@router.post("/jobs/{id}/stop",dependencies=[Depends(require_origin)])
def stop(id:str,db:Session=Depends(get_db)):
    j=get_job(db,id)
    if j.state=="running":
        try:qoder.request("POST","/chat/"+j.id+"/cancel",{})
        except HTTPException as e:
            if e.status_code!=404:raise
        sync(db,j)
    return view(j,True)
@router.put("/jobs/{id}",dependencies=[Depends(require_origin)])
def review(id:str,body:Review,db:Session=Depends(get_db),user:User=Depends(current_user)):
    j=get_job(db,id)
    if j.state!="review" or j.revision!=body.revision:raise HTTPException(409,"草稿版本冲突")
    if len({b.uid for b in body.items})!=len(body.items) or any(b.kind not in ("question","knowledge") or not b.title.strip() or not b.content.strip() or b.resource_id or b.file_id for b in body.items):raise HTTPException(422,"草稿条目无效")
    j.items=[b.model_dump() for b in body.items];j.revision+=1;j.updated_at=now();audit(db,"intelligence.review",user.id);db.commit();return view(j,True)
@router.post("/jobs/{id}/document",dependencies=[Depends(require_origin)])
def convert(id:str,body:Confirm,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);j=get_job(db,id)
    if j.document_id:return {"document_id":j.document_id}
    if j.state!="review" or j.revision!=body.revision or not j.items:raise HTTPException(409,"请先审核草稿")
    draft=docs.Draft(title=j.title,subject=j.subject,blocks=j.items)
    d=TeachingDocument(id=str(uuid4()),title=j.title,kind="intake",subject=j.subject,source_id=None,blocks=docs.validate(db,draft,[]),revision=1,archived=False,created_at=now(),updated_at=now())
    db.add(d);db.flush();docs.references(db,d);j.document_id=d.id;j.state="converted";j.revision+=1;j.updated_at=now();audit(db,"intelligence.convert",user.id);db.commit();return {"document_id":d.id}

class PDFRequest(BaseModel):
    file_id:str=Field(min_length=1,max_length=36)
    start:int=Field(default=1,ge=1,le=10000)
    end:int=Field(default=1,ge=1,le=10000)

@router.post("/pdf-text",dependencies=[Depends(require_origin)])
def pdf_text(body:PDFRequest,db:Session=Depends(get_db)):
    f=db.get(StoredFile,body.file_id)
    if not f:raise HTTPException(404,"文件不存在")
    return {"text":extract_pdf(f,body.start,body.end),"file_id":f.id,"start":body.start,"end":body.end}
