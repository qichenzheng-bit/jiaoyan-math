import json
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user,require_origin,now,audit
from app.core.solution_methods import normalize_subject, parse_methods, format_methods
from app.core.content_normalization import canonical_text
from app.models import IntakeJob as Job, TeachingDocument, StoredFile, User, ChatMessage, ChatSession, IntakeImport, IntakeSupplement
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
    import_reviewed:bool=False
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
        if record.metadata_json.get("warnings") and not body.import_reviewed:
            raise HTTPException(422,"请先核对原始文件及提取警告")
        return {"kind":"file_import","intent":body.intent,"import_id":record.id,"file_id":file.id,
                "file_name":file.name,"sha256":file.sha256,"edited":record.text!=body.text,"import_reviewed":body.import_reviewed,**record.metadata_json}
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
    if db.scalar(select(IntakeSupplement.id).where(IntakeSupplement.job_id==j.id,IntakeSupplement.state.in_(("running","review"))).limit(1)):
        raise HTTPException(409,"请先处理或舍弃待审核的AI补充建议")
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

# Supplemental generation is separate from source-only extraction.
SupplementField=Literal["answer","solution","analysis","proof","alternate"]
LIMITS={"answer":20000,"solution":50000,"analysis":50000,"proof":50000,"alternate":20000}
class SupplementStart(Confirm):
    item_uid:str=Field(min_length=1,max_length=36)
    fields:list[SupplementField]=Field(min_length=1,max_length=5)
    instruction:str=Field(default="",max_length=2000)
class SupplementAccept(Confirm):
    fields:list[SupplementField]=Field(min_length=1,max_length=5)

def allowed_supplements(item):
    fields=["answer","solution","analysis"] if item["kind"]=="question" else ["proof","analysis"]
    result=[k for k in fields if not item.get(k,"").strip()]
    if item["kind"]=="question" and parse_methods(item.get("solution")):result.append("alternate")
    return result

def parse_supplement(raw,fields):
    raw=raw.strip()
    fence=chr(96)*3
    if raw.startswith(fence+"json") and raw.endswith(fence):raw=raw[7:-3].strip()
    data=json.loads(raw)
    if not isinstance(data,dict) or not data or set(data)-set(fields):raise ValueError("unexpected fields")
    result={}
    for k,v in data.items():
        if not isinstance(v,str) or not v.strip() or len(v)>LIMITS[k] or "\x00" in v:raise ValueError("invalid supplement")
        result[k]=v.strip()
    return result

def apply_supplement(item,proposal,fields):
    if len(set(fields))!=len(fields) or not set(fields)<=set(proposal) or not set(fields)<=set(allowed_supplements(item)):
        raise HTTPException(409,"补充字段已变化或不是允许的缺失字段")
    result=dict(item)
    for k in fields:
        if k!="alternate":result[k]=proposal[k]
        else:
            prior=parse_methods(item.get("solution"))
            incoming=parse_methods(proposal[k])
            existing={canonical_text(m["body"]) for m in prior}
            added=[]
            for method in incoming:
                key=canonical_text(method["body"])
                if key and key not in existing:
                    added.append({"body":method["body"],"recommended":False})
                    existing.add(key)
            if not added:raise HTTPException(422,"备选解法与原有解法重复")
            result["solution"]=format_methods(prior+added,always_headers=True)
            if len(result["solution"])>LIMITS["solution"]:raise HTTPException(422,"合并后解析过长")
    return docs.Block.model_validate(result).model_dump()

def supplement_view(s):
    return {k:getattr(s,k) for k in ("id","job_id","item_uid","base_revision","fields","instruction","model","state","detail","proposal","accepted","created_at","updated_at")}

def find_supplement(db,job_id,ident):
    s=db.scalar(select(IntakeSupplement).where(IntakeSupplement.job_id==job_id,IntakeSupplement.id==ident).with_for_update())
    if not s:raise HTTPException(404,"补充建议不存在")
    return s

def sync_supplement(db,s):
    if s.state!="running":return
    try:r=qoder.request("GET","/chat/"+s.id)
    except HTTPException as e:
        if (e.status_code==404 and now()-s.created_at>15) or now()-s.created_at>300:
            s.state="failed";s.detail="补充任务已失效，请重新发起"
        else:return
    else:
        state=r.get("state")
        if state=="running":return
        if state=="done":
            try:s.proposal=parse_supplement(r.get("answer",""),s.fields);s.state="review";s.detail="AI生成内容待人工核对，尚未合并"
            except (ValueError,TypeError):s.state="failed";s.detail="补充结果格式无效，请重新发起"
        else:s.state="stopped" if state=="stopped" else "failed";s.detail=str(r.get("detail","执行失败"))[:400]
    s.updated_at=now();db.commit()

@router.get("/jobs/{id}/supplements")
def supplements(id:str,db:Session=Depends(get_db)):
    j=get_job(db,id)
    rows=list(db.scalars(select(IntakeSupplement).where(IntakeSupplement.job_id==j.id).order_by(IntakeSupplement.created_at.desc(),IntakeSupplement.id).limit(100)))
    for s in rows:
        if s.state=="running":sync_supplement(db,s)
    return [supplement_view(s) for s in rows]

@router.post("/jobs/{id}/supplements",dependencies=[Depends(require_origin)])
def supplement_start(id:str,body:SupplementStart,db:Session=Depends(get_db),user:User=Depends(current_user)):
    j=get_job(db,id)
    if j.state!="review" or j.revision!=body.revision:raise HTTPException(409,"草稿版本冲突，请先保存")
    if db.scalar(select(IntakeSupplement.id).where(IntakeSupplement.job_id==j.id,IntakeSupplement.state.in_(("running","review"))).limit(1)):
        raise HTTPException(409,"请先处理当前AI补充建议")
    item=next((x for x in j.items if x["uid"]==body.item_uid),None)
    if not item or len(set(body.fields))!=len(body.fields) or not set(body.fields)<=set(allowed_supplements(item)):
        raise HTTPException(422,"只能补充缺失字段或追加不同解法")
    payload=json.dumps({k:item.get(k,"") for k in ("kind","title","content","answer","solution","analysis","proof","chapter")},ensure_ascii=False)
    prompt=("你是微光数学教研助手。本任务是用户明确授权的AI补充，不属于原文。只针对提供的题目或知识单元生成指定字段，不修改题干或已有答案。"
        "缺少必要图形、条件或无法确定时不要猜测；可以省略无法完成的字段。解析要完整逐步推导；备选解法必须实质不同，保留已有解法。"
        "所有公式使用LaTeX定界符，JSON正确转义。仅输出JSON对象，键只能来自指定字段，值必须为非空字符串；不输出其他字段。"
        "\n指定字段："+json.dumps(body.fields)+"\n用户补充要求："+body.instruction+"\n【已审核草稿数据】\n"+payload+"\n【数据结束】")
    if len(prompt.encode("utf-8"))>100000:raise HTTPException(422,"题目内容过长，请缩小补充范围")
    if not qoder.request("GET","/status").get("chat_available"):raise HTTPException(503,"Qoder执行服务未就绪")
    s=IntakeSupplement(id=str(uuid4()),job_id=j.id,item_uid=body.item_uid,base_revision=j.revision,base_item=item,
        fields=body.fields,instruction=body.instruction,model=j.model,state="running",detail="",proposal={},accepted=[],created_at=now(),updated_at=now())
    db.add(s);audit(db,"intelligence.supplement.start",user.id);db.commit()
    try:qoder.request("POST","/chat/start",{"id":s.id,"model":s.model,"prompt":prompt})
    except HTTPException as e:
        if e.status_code not in (503,504):
            s=find_supplement(db,id,s.id);s.state="failed";s.detail=str(e.detail)[:400];s.updated_at=now();db.commit()
    return supplement_view(s)

@router.post("/jobs/{id}/supplements/{ident}/accept",dependencies=[Depends(require_origin)])
def supplement_accept(id:str,ident:str,body:SupplementAccept,db:Session=Depends(get_db),user:User=Depends(current_user)):
    j=get_job(db,id);s=find_supplement(db,id,ident)
    if s.state=="accepted":return view(j,True)
    if j.state!="review" or j.revision!=body.revision or s.state!="review" or s.base_revision!=j.revision:
        raise HTTPException(409,"草稿已修改或建议不再有效，请舍弃后重新生成")
    item=next((x for x in j.items if x["uid"]==s.item_uid),None)
    if item!=s.base_item:raise HTTPException(409,"原条目已变化")
    replacement=apply_supplement(item,s.proposal,body.fields)
    j.items=[replacement if x["uid"]==s.item_uid else x for x in j.items]
    j.revision+=1;j.updated_at=now();s.accepted=body.fields;s.state="accepted";s.updated_at=now()
    audit(db,"intelligence.supplement.accept",user.id);db.commit();return view(j,True)

@router.post("/jobs/{id}/supplements/{ident}/discard",dependencies=[Depends(require_origin)])
def supplement_discard(id:str,ident:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    get_job(db,id);s=find_supplement(db,id,ident)
    if s.state=="running":
        try:qoder.request("POST","/chat/"+s.id+"/cancel",{})
        except HTTPException as e:
            if e.status_code!=404:raise
        s.state="discarded"
    elif s.state=="review":s.state="discarded"
    else:raise HTTPException(409,"此建议无需舍弃")
    s.updated_at=now();audit(db,"intelligence.supplement.discard",user.id);db.commit();return supplement_view(s)
