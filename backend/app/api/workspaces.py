"""Persistent file workspaces. Each explicit batch is bounded and resumable one unit at a time."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, now, audit
from app.models import WorkSession, WorkMaterial, WorkBatch, StoredFile, IntakeImport, IntakeJob, User
from app.services import storage, material_import as imp
from app.api import intelligence as ai

router=APIRouter(prefix="/workspaces",dependencies=[Depends(current_user)])
class Create(BaseModel):
    title:str=Field(min_length=1,max_length=200)
class Attach(BaseModel):
    file_ids:list[str]=Field(min_length=1,max_length=20)
class Range(BaseModel):
    start:int=Field(ge=1,le=10000)
    end:int=Field(ge=1,le=10000)
class Verify(BaseModel):
    text:str=Field(min_length=1,max_length=24000)
class Organize(BaseModel):
    model:str=Field(default="Auto",max_length=80,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
    effort:str|None=Field(default=None,max_length=16)
    source_id:str|None=Field(default=None,max_length=36)
    subject:str=Field(default="",max_length=40)

def workspace(db,ident,lock=False):
    q=select(WorkSession).where(WorkSession.id==ident)
    s=db.scalar(q.with_for_update() if lock else q)
    if not s:raise HTTPException(404,"工作会话不存在")
    return s
def material(db,s,ident):
    m=db.get(WorkMaterial,ident)
    if not m or m.session_id!=s.id:raise HTTPException(404,"资料不存在")
    return m
def batch(db,s,ident,lock=False):
    q=select(WorkBatch).join(WorkMaterial,WorkMaterial.id==WorkBatch.material_id).where(WorkBatch.id==ident,WorkMaterial.session_id==s.id)
    b=db.scalar(q.with_for_update(of=WorkBatch) if lock else q)
    if not b:raise HTTPException(404,"识别批次不存在")
    return b
def file_for(db,m):
    f=db.get(StoredFile,m.file_id)
    if not f or f.archived:raise HTTPException(404,"原始文件不可用")
    return f
def pdf_pages(f):
    exe=shutil.which("pdfinfo");limiter=shutil.which("prlimit")
    if not exe or not limiter:return None
    try:
        r=subprocess.run([limiter,"--as=536870912","--cpu=5","--fsize=65536","--",exe,str(storage.file_path(f))],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=8,check=False,env={"PATH":"/usr/bin:/bin","LC_ALL":"C"})
        match=re.search(rb"^Pages:\s+(\d+)",r.stdout,re.M)
        return int(match.group(1)) if r.returncode==0 and match else None
    except (OSError,subprocess.TimeoutExpired):return None
def unit_count(f):
    if f.media_type=="application/pdf":return pdf_pages(f)
    if f.media_type==imp.DOCX:return len(imp.docx_blocks(storage.file_path(f))[0])
    if f.media_type in imp.TEXT or f.media_type in storage.IMAGE_TYPES:return 1
    raise HTTPException(415,"仅支持PDF、DOCX、文本与图片")
def session_view(s):return {"id":s.id,"title":s.title,"created_at":s.created_at,"updated_at":s.updated_at}
def batch_view(db,b,full=False):
    j=db.get(IntakeJob,b.job_id) if b.job_id else None
    result={"id":b.id,"material_id":b.material_id,"start":b.start,"end":b.end,"units":[{k:v for k,v in u.items() if full or k!="text"} for u in b.units],"verified":b.verified_text is not None,"job_id":b.job_id,"job_state":j.state if j else None,"document_id":j.document_id if j else None,"created_at":b.created_at}
    if full:result["verified_text"]=b.verified_text
    return result
def material_view(db,m):
    f=file_for(db,m)
    batches=list(db.scalars(select(WorkBatch).where(WorkBatch.material_id==m.id).order_by(WorkBatch.start,WorkBatch.created_at)))
    done={n for b in batches if b.verified_text is not None for n in range(b.start,b.end+1)}
    next_unit=1
    while next_unit in done:next_unit+=1
    return {"id":m.id,"file":storage.serialize(f),"total_units":m.total_units,"verified_units":len(done),"next_unit":next_unit,"batches":[batch_view(db,b) for b in batches]}

@router.get("")
def listing(db:Session=Depends(get_db)):
    return [session_view(s) for s in db.scalars(select(WorkSession).order_by(WorkSession.updated_at.desc()).limit(100))]
@router.post("",dependencies=[Depends(require_origin)])
def create(body:Create,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not body.title.strip():raise HTTPException(422,"请输入工作名称")
    s=WorkSession(id=str(uuid4()),title=body.title.strip(),created_at=now(),updated_at=now());db.add(s);audit(db,"work.create",user.id);db.commit()
    return session_view(s)
@router.get("/{ident}")
def read(ident:str,db:Session=Depends(get_db)):
    s=workspace(db,ident)
    return {**session_view(s),"materials":[material_view(db,m) for m in db.scalars(select(WorkMaterial).where(WorkMaterial.session_id==s.id).order_by(WorkMaterial.created_at,WorkMaterial.id))]}
@router.post("/{ident}/materials",dependencies=[Depends(require_origin)])
def attach(ident:str,body:Attach,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True)
    existing={m.file_id for m in db.scalars(select(WorkMaterial).where(WorkMaterial.session_id==s.id))}
    for fid in dict.fromkeys(body.file_ids):
        if fid in existing:continue
        f=db.get(StoredFile,fid)
        if not f or f.archived:raise HTTPException(404,"文件不存在")
        total=unit_count(f)
        m=WorkMaterial(id=str(uuid4()),session_id=s.id,file_id=f.id,total_units=total,created_at=now());db.add(m)
        storage.link_file(db,f.id,"work_material",m.id)
    s.updated_at=now();audit(db,"work.attach",user.id);db.commit()
    return read(ident,db)
@router.post("/{ident}/materials/{mid}/batches",dependencies=[Depends(require_origin)])
def create_batch(ident:str,mid:str,body:Range,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True);m=material(db,s,mid);f=file_for(db,m)
    limit=10 if f.media_type=="application/pdf" else 100 if f.media_type==imp.DOCX else 1
    if body.end<body.start or body.end-body.start+1>limit or (m.total_units is not None and body.end>m.total_units) or (limit==1 and body.start!=1):
        raise HTTPException(422,"识别范围无效或超过单批限制")
    rows=list(db.scalars(select(WorkBatch).where(WorkBatch.material_id==m.id)))
    for b in rows:
        if b.start==body.start and b.end==body.end:return batch_view(db,b,True)
        if b.start<=body.end and body.start<=b.end:raise HTTPException(409,"范围与已有批次重叠，请打开已有批次")
        if b.verified_text is None:raise HTTPException(409,"请先完成此资料的上一批核对")
    b=WorkBatch(id=str(uuid4()),material_id=m.id,start=body.start,end=body.end,units=[],created_at=now(),updated_at=now());db.add(b);s.updated_at=now();db.commit()
    return batch_view(db,b,True)
@router.get("/{ident}/batches/{bid}")
def read_batch(ident:str,bid:str,db:Session=Depends(get_db)):
    return batch_view(db,batch(db,workspace(db,ident),bid),True)
@router.post("/{ident}/batches/{bid}/step",dependencies=[Depends(require_origin)])
def step(ident:str,bid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True);b=batch(db,s,bid,True);m=material(db,s,b.material_id);f=file_for(db,m)
    if b.verified_text is not None:return batch_view(db,b,True)
    existing={u["unit"]:u for u in b.units}
    n=next((n for n in range(b.start,b.end+1) if existing.get(n,{}).get("state")!="done"),None)
    if n is None:return batch_view(db,b,True)
    try:
        if f.media_type in storage.IMAGE_TYPES:result=imp.extract(f,"ocr",n,n)
        elif f.media_type=="application/pdf":
            try:result=imp.extract(f,"text",n,n)
            except HTTPException as exc:
                if exc.status_code!=422 or not imp.capabilities()["pdf_ocr"]:raise
                result=imp.extract(f,"ocr",n,n)
        else:result=imp.extract(f,"text",n,n)
        u={"unit":n,"state":"done","text":result["text"],"method":result["method"],"warnings":result.get("warnings",[])}
    except HTTPException as exc:
        u={"unit":n,"state":"failed","error":str(exc.detail)[:400]}
    existing[n]=u;b.units=sorted(existing.values(),key=lambda x:x["unit"]);b.updated_at=now();s.updated_at=now();db.commit()
    return batch_view(db,b,True)
@router.post("/{ident}/batches/{bid}/verify",dependencies=[Depends(require_origin)])
def verify(ident:str,bid:str,body:Verify,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True);b=batch(db,s,bid,True)
    if b.verified_text is not None:
        if b.verified_text!=body.text:raise HTTPException(409,"此批已核对，不可覆盖")
        return batch_view(db,b,True)
    if {u["unit"] for u in b.units if u["state"]=="done"}!=set(range(b.start,b.end+1)) or not body.text.strip():raise HTTPException(409,"请先识别完整批次")
    m=material(db,s,b.material_id);warnings=sorted({w for u in b.units for w in u.get("warnings",[])})
    record=IntakeImport(id=str(uuid4()),file_id=m.file_id,text=body.text,metadata_json={"method":"work_batch","start":b.start,"end":b.end,"total_units":m.total_units,"warnings":warnings},created_at=now());db.add(record);db.flush()
    b.verified_text=body.text;b.import_id=record.id;b.updated_at=now();s.updated_at=now();audit(db,"work.verify",user.id);db.commit()
    return batch_view(db,b,True)
@router.post("/{ident}/batches/{bid}/organize",dependencies=[Depends(require_origin)])
def organize(ident:str,bid:str,body:Organize,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True);b=batch(db,s,bid,True)
    if b.job_id:return ai.view(db.get(IntakeJob,b.job_id),True)
    if not b.verified_text or not b.import_id:raise HTTPException(409,"请先核对识别原文")
    m=material(db,s,b.material_id);f=file_for(db,m)
    start=ai.Start(title=(f.name+" · "+str(b.start)+"–"+str(b.end))[:200],subject=body.subject,text=b.verified_text,model=body.model,effort=body.effort,source_id=body.source_id,import_id=b.import_id,import_reviewed=True)
    provenance={**ai.build_provenance(db,start),"workspace_id":s.id,"work_batch_id":b.id,"work_material_id":m.id,"file_media_type":f.media_type,"reviewed_uids":[]}
    s.updated_at=now()
    return ai.launch(db,user,start,provenance,work_batch=b)
@router.get("/{ident}/materials/{mid}/page")
def page(ident:str,mid:str,unit:int=Query(ge=1,le=10000),db:Session=Depends(get_db)):
    m=material(db,workspace(db,ident),mid);f=file_for(db,m)
    if f.media_type!="application/pdf":raise HTTPException(415,"仅PDF支持物理页预览")
    if m.total_units is not None and unit>m.total_units:raise HTTPException(422,"页码超出范围")
    with tempfile.TemporaryDirectory(prefix="work-preview-") as tmp:
        prefix=str(Path(tmp)/"page")
        imp.bounded_command([shutil.which("pdftoppm"),"-f",str(unit),"-l",str(unit),"-singlefile","-scale-to","1800","-png",str(storage.file_path(f)),prefix],12)
        path=Path(prefix+".png")
        if not path.is_file() or path.stat().st_size>10_000_000:raise HTTPException(422,"原页预览不可用")
        return Response(path.read_bytes(),media_type="image/png",headers={"Content-Security-Policy":"sandbox; default-src 'none'"})
