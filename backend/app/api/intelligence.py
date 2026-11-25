import json
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user,require_origin,now,audit
from app.core.solution_methods import normalize_subject
from app.models import IntakeJob as Job, TeachingDocument, StoredFile, User, ChatMessage, ChatSession, IntakeImport
from app.services.pdf_text import extract_pdf
from app.services import material_import, storage
from app.api import qoder, documents as docs, resources as bank

router=APIRouter(prefix="/intelligence",dependencies=[Depends(current_user)])
class Start(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    subject:str=Field(default="",max_length=40)
    text:str=Field(min_length=1,max_length=24000)
    model:str=Field(default="Auto",max_length=80,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
    import_id:str|None=Field(default=None,max_length=36)
    source_message_id:str|None=Field(default=None,max_length=36)
    source_id:str|None=Field(default=None,max_length=36)
    input_origin:Literal["manual","chat_draft"]="manual"
    intent:Literal["mixed","question","knowledge","document"]="mixed"
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
    r={k:getattr(j,k) for k in ("id","title","subject","model","state","detail","document_id","revision","created_at","updated_at","source_id")}
    r.update(provenance=j.provenance or {},retry_of=j.retry_of)
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
def chat_source(db,ident):
    message=db.get(ChatMessage,ident)
    if not message or message.role not in ("user","assistant") or message.state!="done":
        raise HTTPException(404,"已完成的来源消息不存在")
    if not message.content.strip() or len(message.content)>24000:
        raise HTTPException(422,"来源正文为空或超过24000字，请手动分批")
    return message

@router.get("/chat-source/{ident}")
def read_chat_source(ident:str,db:Session=Depends(get_db)):
    m=chat_source(db,ident)
    session=db.get(ChatSession,m.session_id)
    return {"message_id":m.id,"session_id":m.session_id,"role":m.role,"text":m.content,
            "title":session.title if session else "聊天内容","has_attachments":bool(m.attachments or m.resource_refs)}

def build_provenance(db,body):
    if body.import_id:
        if body.source_message_id:raise HTTPException(422,"请选择单一输入来源")
        record=db.get(IntakeImport,body.import_id)
        if not record:raise HTTPException(404,"导入记录不存在")
        file=db.get(StoredFile,record.file_id)
        if not file or file.archived:raise HTTPException(422,"原始文件已归档")
        return {"kind":"file_import","intent":body.intent,"import_id":record.id,"file_id":file.id,
                "file_name":file.name,"sha256":file.sha256,"edited":record.text!=body.text,**record.metadata_json}
    if body.source_message_id:
        m=chat_source(db,body.source_message_id)
        return {"kind":"chat_"+m.role,"session_id":m.session_id,"message_id":m.id,
                "edited":body.text!=m.content,"intent":body.intent}
    return {"kind":body.input_origin,"intent":body.intent}

def launch(db,user,body,provenance,retry_of=None):
    if not body.title.strip() or not body.text.strip():raise HTTPException(422,"标题和原文不能为空")
    if body.source_id:bank.active_source(db,body.source_id,True)
    prompt="你是数学资料录入助手。仅依据原文提取题目与知识单元，不补造答案、证明或图形。保持数学含义、LaTeX、多种解法；标题、正文、答案、解析、证明、标签中的所有数学表达式均使用标准LaTeX定界符（行内单美元符号，独立双美元符号），JSON正确转义反斜线，禁止将公式转换成普通字符，连续页跨页题干合并。无法确认的字段留空或在analysis标记待核对。仅输出JSON数组，每项kind(question或knowledge),title,content,answer,solution,analysis,proof,chapter,question_type,unit_type。最多100项。\n学科："+body.subject+"\n【原文】\n"+body.text+"\n【原文结束】"
    intent=provenance.get("intent","mixed")
    focus={"question":"优先提取题目及原文已有答案解析。","knowledge":"优先提取知识单元及原文已有证明。","document":"按原文顺序整理整套资料中的题目和知识单元。","mixed":"按原文实际内容识别题目和知识单元。"}[intent]
    prompt+="\n【本次整理目标】"+focus
    if provenance.get("kind")=="chat_assistant":prompt+="\n来源是AI生成回复，不是原始文献；只能整理为待核对草稿。"
    if provenance.get("kind")=="file_import" and provenance.get("warnings"):
        prompt+="\n文件提取可能失真。保留不确定标记，不自行还原缺失公式、图形或答案。所有结果待人工对照原件。"
    if len(prompt.encode("utf-8"))>100000:raise HTTPException(422,"原文过长")
    if not qoder.request("GET","/status").get("chat_available"):raise HTTPException(503,"独立Qoder执行服务需升级至V3")
    j=Job(id=str(uuid4()),title=body.title.strip(),subject=normalize_subject(body.subject),input_text=body.text,model=body.model,state="running",detail="",items=[],document_id=None,source_id=body.source_id,provenance=provenance,retry_of=retry_of,revision=1,created_at=now(),updated_at=now())
    db.add(j);db.flush()
    if provenance.get("kind")=="file_import":
        storage.link_file(db,provenance["file_id"],"intake_job",j.id)
    audit(db,"intelligence.start" if not retry_of else "intelligence.retry",user.id);db.commit()
    try:qoder.request("POST","/chat/start",{"id":j.id,"model":j.model,"prompt":prompt})
    except HTTPException as e:
        # Ambiguous transport failures may occur after acceptance. Reconcile the original ID.
        if e.status_code not in (503,504):
            j=get_job(db,j.id);j.state="failed";j.detail=str(e.detail)[:400];j.revision+=1;j.updated_at=now();db.commit()
    return view(j,True)

@router.post("/jobs",dependencies=[Depends(require_origin)])
def start(body:Start,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return launch(db,user,body,build_provenance(db,body))

@router.post("/jobs/{id}/retry",dependencies=[Depends(require_origin)])
def retry(id:str,body:Confirm,db:Session=Depends(get_db),user:User=Depends(current_user)):
    j=get_job(db,id)
    existing=db.scalar(select(Job).where(Job.retry_of==j.id))
    if existing:return view(existing,True)
    if j.state not in ("failed","stopped") or j.revision!=body.revision:
        raise HTTPException(409,"仅失败或已停止任务可重试，请刷新任务状态")
    provenance=j.provenance or {"kind":"manual","intent":"mixed"}
    draft=Start(title=j.title,subject=j.subject,text=j.input_text,model=j.model,source_id=j.source_id)
    return launch(db,user,draft,provenance,retry_of=j.id)

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
    draft=docs.Draft(title=j.title,subject=j.subject,source_id=j.source_id,blocks=j.items)
    d=TeachingDocument(id=str(uuid4()),title=j.title,kind="intake",subject=j.subject,source_id=j.source_id,blocks=docs.validate(db,draft,[]),revision=1,archived=False,created_at=now(),updated_at=now())
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

class MaterialRequest(PDFRequest):
    mode:Literal["text","ocr"]="text"

@router.get("/import/capabilities")
def import_capabilities():
    return material_import.capabilities()

@router.post("/import",dependencies=[Depends(require_origin)])
def import_material(body:MaterialRequest,db:Session=Depends(get_db),user:User=Depends(current_user)):
    file=db.get(StoredFile,body.file_id)
    if not file:raise HTTPException(404,"文件不存在")
    result=material_import.extract(file,body.mode,body.start,body.end)
    record=IntakeImport(id=str(uuid4()),file_id=file.id,text=result["text"],
        metadata_json={k:v for k,v in result.items() if k!="text"},created_at=now())
    db.add(record);audit(db,"intelligence.import",user.id);db.commit()
    return {**result,"import_id":record.id,"file_id":file.id,"file_name":file.name}

@router.get("/import/{ident}")
def import_detail(ident:str,db:Session=Depends(get_db)):
    record=db.get(IntakeImport,ident)
    if not record:raise HTTPException(404,"导入记录不存在")
    file=db.get(StoredFile,record.file_id)
    if not file:raise HTTPException(404,"原始文件不存在")
    return {**record.metadata_json,"import_id":record.id,"file_id":file.id,"file_name":file.name,"text":record.text}
