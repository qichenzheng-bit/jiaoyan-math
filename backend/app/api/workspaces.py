from typing import Literal
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
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, now, audit
from app.models import WorkSession, WorkMaterial, WorkBatch, StoredFile, IntakeImport, IntakeJob, User, FileReference, TeachingDocument, DocumentRegistration, IntakeSupplement
from app.services import storage, material_import as imp, material_vision as vision, word_images
from app.services.recognition_plan import parse_instruction, matching_names, propose_range
from app.api import intelligence as ai
from app.api import work_agent as agent

router=APIRouter(prefix="/workspaces",dependencies=[Depends(current_user)])
class Create(BaseModel):
    title:str=Field(min_length=1,max_length=200)
class Attach(BaseModel):
    file_ids:list[str]=Field(min_length=1,max_length=20)
    image_sequence:bool=False
class Range(BaseModel):
    start:int=Field(ge=1,le=10000)
    end:int=Field(ge=1,le=10000)
class Verify(BaseModel):
    text:str=Field(min_length=1,max_length=24000)
class Organize(BaseModel):
    intent:str=Field(default='mixed',pattern='^(mixed|question|knowledge|document)$')
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
    attached=select(WorkMaterial.file_id).where(WorkMaterial.session_id==s.id)
    q=select(WorkBatch).join(WorkMaterial,WorkMaterial.id==WorkBatch.material_id).where(WorkBatch.id==ident,WorkMaterial.file_id.in_(attached))
    b=db.scalar(q.with_for_update(of=WorkBatch) if lock else q)
    if not b:raise HTTPException(404,"识别批次不存在")
    return b
def file_for(db,m,lock=False):
    f=db.scalar(select(StoredFile).where(StoredFile.id==m.file_id).with_for_update()) if lock else db.get(StoredFile,m.file_id)
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
def session_view(s):
    # Include agent-started intake children even for legacy jobs without provenance.
    ids=set()
    for record in s.agent_history or []:
        child=record.get("child") or {}
        if child.get("kind")=="intake" and child.get("id"):ids.add(child["id"])
        for step in record.get("steps") or []:
            result=step.get("result") or {}
            if step.get("tool") in ("intake_text","native_intake_review","native_text_review") and isinstance(result,dict) and result.get("id"):ids.add(result["id"])
    return {"id":s.id,"title":s.title,"created_at":s.created_at,"updated_at":s.updated_at,"intake_job_ids":sorted(ids)}
def latest_job(db,b):
    j=db.get(IntakeJob,b.job_id) if b.job_id else None
    seen=set()
    while j and j.id not in seen:
        seen.add(j.id)
        successor=db.scalar(select(IntakeJob).where(IntakeJob.retry_of==j.id))
        if not successor:break
        j=successor
    return j
def registered(db,j):
    if not j or j.state!="converted" or not j.document_id or not j.items:return False
    d=db.get(TeachingDocument,j.document_id)
    if not d or d.archived:return False
    refs={b["uid"] for b in d.blocks if b.get("kind")=="reference" and b.get("resource_id") and not b.get("edit_reference_revision")}
    history={entry.get("uid") for r in db.scalars(select(DocumentRegistration).where(DocumentRegistration.document_id==d.id)) for entry in r.entries}
    return all(b.get("uid") in refs and b.get("uid") in history for b in j.items)
def file_batches(db,fid):
    return list(db.scalars(select(WorkBatch).join(WorkMaterial,WorkMaterial.id==WorkBatch.material_id).where(WorkMaterial.file_id==fid).order_by(WorkBatch.start,WorkBatch.created_at)))
def chunks(values,size=500):
    values=list(values)
    for i in range(0,len(values),size):yield values[i:i+size]

def batch_groups(db,file_ids):
    """Load historical batches once for the files in the current response."""
    grouped={fid:[] for fid in file_ids}
    for ids in chunks(grouped):
        stmt=select(WorkMaterial.file_id,WorkBatch).join(WorkBatch,WorkBatch.material_id==WorkMaterial.id).where(WorkMaterial.file_id.in_(ids)).order_by(WorkBatch.start,WorkBatch.created_at)
        for fid,b in db.execute(stmt):grouped[fid].append(b)
    return grouped

def batch_states(db,batches):
    """Bulk load retry chains and registration evidence without repeated per-batch queries."""
    roots={b.job_id for b in batches if b.job_id}
    jobs={};successors={}
    cols=(IntakeJob.id,IntakeJob.retry_of,IntakeJob.state,IntakeJob.document_id,IntakeJob.items,IntakeJob.provenance)
    for ids in chunks(roots):
        for j in db.execute(select(*cols).where(IntakeJob.id.in_(ids))):jobs[j.id]=j
    pending=set(jobs);visited=set()
    while pending:
        visited.update(pending);following=set()
        for ids in chunks(pending):
            for j in db.execute(select(*cols).where(IntakeJob.retry_of.in_(ids))):
                successors[j.retry_of]=j.id;jobs[j.id]=j
                if j.id not in visited:following.add(j.id)
        pending=following
    latest={}
    for b in batches:
        j=jobs.get(b.job_id);seen=set()
        while j and j.id not in seen and j.id in successors:
            seen.add(j.id);j=jobs[successors[j.id]]
        latest[b.id]=j
    doc_ids={j.document_id for j in latest.values() if j and j.state=="converted" and j.document_id and j.items}
    refs={};history={}
    for ids in chunks(doc_ids):
        for did,blocks in db.execute(select(TeachingDocument.id,TeachingDocument.blocks).where(TeachingDocument.id.in_(ids),TeachingDocument.archived==False)):
            refs[did]={b["uid"] for b in blocks if b.get("kind")=="reference" and b.get("resource_id") and not b.get("edit_reference_revision")}
        for did,entries in db.execute(select(DocumentRegistration.document_id,DocumentRegistration.entries).where(DocumentRegistration.document_id.in_(ids))):
            history.setdefault(did,set()).update(entry.get("uid") for entry in entries)
    saved={bid for bid,j in latest.items() if j and j.state=="converted" and j.document_id in refs and j.items and all(b.get("uid") in refs[j.document_id] and b.get("uid") in history.get(j.document_id,set()) for b in j.items)}
    return latest,saved

def reviewed_batch(j):
    return bool(j and j.state=="converted" and (j.provenance or {}).get("single_review"))

def progress(db,f,batches,total,states=None):
    states=states if states is not None else batch_states(db,batches)
    done={n for b in batches if b.verified_text is not None or reviewed_batch(states[0].get(b.id)) for n in range(b.start,b.end+1)}
    recognized={u["unit"] for b in batches for u in b.units if u.get("state")=="done"}
    registered_ids=states[1]
    saved={n for b in batches if b.id in registered_ids for n in range(b.start,b.end+1)}
    next_unit=1
    while next_unit in done:next_unit+=1
    return {"total_units":total,"recognized_units":len(recognized),"verified_units":len(done),"registered_units":len(saved),"next_unit":next_unit,"complete":total is not None and total>0 and sum(1 for n in saved if 1<=n<=total)==total}
def batch_view(db,b,full=False,states=None):
    j=latest_job(db,b) if states is None else states[0].get(b.id)
    result={"id":b.id,"material_id":b.material_id,"start":b.start,"end":b.end,"units":[{k:v for k,v in u.items() if k!="image_results" and (full or k!="text")} for u in b.units],"verified":b.verified_text is not None,"item_reviewed":reviewed_batch(j),"job_id":j.id if j else None,"job_state":j.state if j else None,"document_id":j.document_id if j else None,"created_at":b.created_at}
    if full:result["verified_text"]=b.verified_text
    return result
def material_view(db,m):
    return material_views(db,[m])[0]

def material_views(db,materials):
    materials=list(materials);ids={m.file_id for m in materials}
    files={f.id:f for part in chunks(ids) for f in db.scalars(select(StoredFile).where(StoredFile.id.in_(part)))}
    grouped=batch_groups(db,ids)
    states=batch_states(db,[b for bs in grouped.values() for b in bs])
    return [{"id":m.id,"file":storage.serialize(files[m.file_id]),**progress(db,files[m.file_id],grouped[m.file_id],m.total_units,states),"batches":[batch_view(db,b,states=states) for b in grouped[m.file_id]]} for m in materials]

SUPPORTED=tuple(sorted({"application/pdf",imp.DOCX,*imp.TEXT,*storage.IMAGE_TYPES}))
class Cleanup(BaseModel):
    file_ids:list[str]=Field(min_length=1,max_length=20)
    allow_unfinished:bool=False

def library_details(db,files):
    files=list(files);ids=[f.id for f in files];totals={}
    for part in chunks(ids):
        stmt=select(WorkMaterial.file_id,WorkMaterial.total_units).where(WorkMaterial.file_id.in_(part)).order_by(WorkMaterial.created_at,WorkMaterial.id)
        for fid,total in db.execute(stmt):totals.setdefault(fid,total)
    grouped=batch_groups(db,ids)
    states=batch_states(db,[b for bs in grouped.values() for b in bs])
    rows=[{**storage.serialize(f),**progress(db,f,grouped[f.id],totals.get(f.id,1 if f.media_type in imp.TEXT or f.media_type in storage.IMAGE_TYPES else None),states)} for f in files]
    return rows,grouped,states

def library_row(db,f):
    return library_details(db,[f])[0][0]
def original_query():
    return select(StoredFile).where(StoredFile.generated==False,StoredFile.media_type.in_(SUPPORTED))
@router.get("/library")
def library(q:str=Query("",max_length=255),archived:bool=False,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),progress_filter:Literal["all","done","todo"]="all"):
    stmt=original_query().where(StoredFile.archived==archived,(StoredFile.purged_at.is_(None)) | (StoredFile.purge_pending==True))
    if q.strip():stmt=stmt.where(StoredFile.name.contains(q.strip(),autoescape=True))
    ordered=stmt.order_by(StoredFile.created_at.desc(),StoredFile.id)
    if progress_filter=="all":
        total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        return {"items":library_details(db,db.scalars(ordered.offset(offset).limit(limit)))[0],"total":total}
    # Completion is derived from authoritative registration state; filter before pagination.
    items=[];total=0
    for part in db.scalars(ordered.execution_options(yield_per=100)).partitions(100):
        for row in library_details(db,part)[0]:
            if row["complete"]!=(progress_filter=="done"):continue
            if offset<=total<offset+limit:items.append(row)
            total+=1
    return {"items":items,"total":total}
@router.get("/library/resolve")
def resolve_library(instruction:str=Query(min_length=1,max_length=500),db:Session=Depends(get_db)):
    # Full filenames or unambiguous complete stems only. Never pick a file by model guess.
    q=instruction.casefold()
    matches=[]
    for f in db.scalars(original_query().where(StoredFile.archived==False)):
        stem=Path(f.name).stem.casefold()
        if f.name.casefold() in q or (len(stem)>=2 and stem in q):
            matches.append(f)
            if len(matches)>=20:break
    return {"items":library_details(db,matches)[0]}
def protect_original(db,f):
    for ref in db.scalars(select(FileReference).where(FileReference.file_id==f.id)):
        if ref.owner_type=="work_material":continue
        if ref.owner_type=="intake_job":
            j=db.get(IntakeJob,ref.owner_id)
            if j and j.state in ("failed","stopped","converted") and (j.state!="converted" or registered(db,j)):continue
        if ref.owner_type=="intake_supplement":
            s=db.get(IntakeSupplement,ref.owner_id);j=db.get(IntakeJob,s.job_id) if s else None
            if s and (s.state in ("failed","stopped","discarded") or s.state=="accepted" and registered(db,j)):continue
        raise HTTPException(409,f.name+" 仍被未完成任务、聊天或正式资源引用")

@router.post("/library/archive",dependencies=[Depends(require_origin)])
def archive_library(body:Cleanup,db:Session=Depends(get_db),user:User=Depends(current_user)):
    ids=sorted(set(body.file_ids))
    for fid in ids:
        f=db.scalar(original_query().where(StoredFile.id==fid).with_for_update())
        if not f:raise HTTPException(404,"原始资料不存在")
        if f.purged_at is not None:raise HTTPException(410,"原始文件已永久清理")
        if f.archived:continue
        row=library_row(db,f)
        if not row["complete"] and not body.allow_unfinished:raise HTTPException(409,f.name+" 尚未全部入库")
        protect_original(db,f)
        f.archived=True
    audit(db,"work.library.archive",user.id);db.commit()
    return {"archived_ids":ids}
@router.post("/library/{fid}/restore",dependencies=[Depends(require_origin)])
def restore_library(fid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    f=db.scalar(original_query().where(StoredFile.id==fid).with_for_update())
    if not f:raise HTTPException(404,"原始资料不存在")
    storage.file_path(f);f.archived=False;audit(db,"work.library.restore",user.id);db.commit()
    return library_row(db,f)

class Purge(BaseModel):
    file_ids:list[str]=Field(min_length=1,max_length=20)
    confirm:bool=False

@router.post("/library/purge",dependencies=[Depends(require_origin)])
def purge_library(body:Purge,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not body.confirm:raise HTTPException(422,"永久清理需要明确确认")
    # A backup holds a shared session lock before taking its database snapshot.
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"),{"key":storage.PURGE_LOCK}):
        raise HTTPException(409,"加密备份正在读取资料，请稍后重试")
    db.scalar(select(User).where(User.id==user.id).with_for_update())
    ids=sorted(set(body.file_ids))
    for fid in ids:
        f=db.scalar(original_query().where(StoredFile.id==fid).with_for_update())
        if not f:raise HTTPException(404,"原始资料不存在")
        if not f.archived:raise HTTPException(409,"请先将资料移入回收区")
        if f.purged_at is not None:continue
        protect_original(db,f)
        # Archive already required separate confirmation of unfinished material.
        f.purged_at=now();f.purge_pending=True
    audit(db,"work.library.purge.mark",user.id);db.commit()
    # Commit the durable tombstone before touching bytes. Future backups exclude these blobs,
    # while all historic FK references remain intact. Crash/failure can be retried idempotently.
    completed=[];pending=[];removed_bytes=0
    for fid in ids:
        f=db.scalar(original_query().where(StoredFile.id==fid).with_for_update())
        if not f.purge_pending:
            completed.append(fid);db.commit();continue
        try:
            storage.remove_purged_original(f)
        except (OSError,ValueError,HTTPException):
            pending.append(fid);db.rollback();continue
        f.purge_pending=False;completed.append(fid);removed_bytes+=f.size_bytes
        audit(db,"work.library.purge.complete",user.id);db.commit()
    return {"purged_ids":completed,"pending_ids":pending,"removed_bytes":removed_bytes}

@router.get("")
def listing(db:Session=Depends(get_db)):
    return [session_view(s) for s in db.scalars(select(WorkSession).order_by(WorkSession.updated_at.desc()).limit(100))]
@router.post("",dependencies=[Depends(require_origin)])
def create(body:Create,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not body.title.strip():raise HTTPException(422,"请输入工作名称")
    s=WorkSession(id=str(uuid4()),title=body.title.strip(),created_at=now(),updated_at=now());db.add(s);audit(db,"work.create",user.id);db.commit()
    return session_view(s)
@router.patch("/{ident}",dependencies=[Depends(require_origin)])
def rename(ident:str,body:Create,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True)
    if not body.title.strip():raise HTTPException(422,"请输入工作名称")
    s.title=body.title.strip();s.updated_at=now();audit(db,"work.rename",user.id);db.commit()
    return session_view(s)

@router.delete("/{ident}",dependencies=[Depends(require_origin)])
def remove(ident:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from app.services.work_removal import remove_workspace
    s=workspace(db,ident,True)
    removed=remove_workspace(db,s,user=user)
    audit(db,"work.delete",user.id);db.commit()
    return {"deleted":True,"id":ident,"removed_job_ids":removed}

@router.get("/{ident}/recognition-plan")
def recognition_plan(ident:str,instruction:str=Query(min_length=1,max_length=500),selected_id:str|None=None,db:Session=Depends(get_db)):
    s=workspace(db,ident)
    try:request=parse_instruction(instruction)
    except ValueError as e:raise HTTPException(422,str(e))
    files=list(db.scalars(original_query().where(StoredFile.archived==False,StoredFile.media_type=="application/pdf").order_by(StoredFile.name,StoredFile.id)))
    candidates=matching_names(files,instruction,request["hint"])
    if not candidates and not request["hint"]:
        if selected_id and not request["unfinished"]:
            m=material(db,s,selected_id)
            candidates=[f for f in files if f.id==m.file_id]
        else:candidates=files
    result=[]
    for f in candidates:
        batches=file_batches(db,f.id);row=library_row(db,f)
        if request["unfinished"] and row["total_units"] is not None and row["verified_units"]>=row["total_units"]:continue
        result.append({"file_id":f.id,"file_name":f.name,**propose_range(request,batches,row["total_units"],row["next_unit"]),"total_units":row["total_units"],"verified_units":row["verified_units"]})
        if len(result)>=21:break
    return {"candidates":result[:20],"more":len(result)>20}

@router.get("/{ident}")
def read(ident:str,db:Session=Depends(get_db)):
    s=workspace(db,ident)
    return {**session_view(s),"materials":material_views(db,db.scalars(select(WorkMaterial).where(WorkMaterial.session_id==s.id).order_by(WorkMaterial.created_at,WorkMaterial.id)))}
@router.post("/{ident}/materials",dependencies=[Depends(require_origin)])
def attach(ident:str,body:Attach,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True)
    existing={m.file_id for m in db.scalars(select(WorkMaterial).where(WorkMaterial.session_id==s.id))}
    ids=list(dict.fromkeys(body.file_ids))
    sequence_id=None
    if body.image_sequence and len(ids)>1:
        from app.services.image_sequence import create_sequence
        sequence_id=create_sequence(db,ids,user.id)
        ids=[sequence_id]
    for fid in ids:
        if fid in existing:continue
        f=db.scalar(original_query().where(StoredFile.id==fid).with_for_update())
        if not f or f.archived:raise HTTPException(404,"文件不存在")
        previous=db.scalar(select(WorkMaterial).where(WorkMaterial.file_id==f.id).limit(1))
        total=previous.total_units if previous and previous.total_units is not None else unit_count(f)
        m=WorkMaterial(id=str(uuid4()),session_id=s.id,file_id=f.id,total_units=total,created_at=now());db.add(m)
        storage.link_file(db,f.id,"work_material",m.id)
    s.updated_at=now();audit(db,"work.attach",user.id);db.commit()
    result=read(ident,db)
    if sequence_id:result["sequence_material_id"]=next(m["id"] for m in result["materials"] if m["file"]["id"]==sequence_id)
    return result
@router.post("/{ident}/materials/{mid}/batches",dependencies=[Depends(require_origin)])
def create_batch(ident:str,mid:str,body:Range,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True);m=material(db,s,mid);f=file_for(db,m,True)
    limit=10 if f.media_type=="application/pdf" else 100 if f.media_type==imp.DOCX else 1
    if body.end<body.start or body.end-body.start+1>limit or (m.total_units is not None and body.end>m.total_units) or (limit==1 and body.start!=1):
        raise HTTPException(422,"识别范围无效或超过单批限制")
    rows=file_batches(db,m.file_id)
    for b in rows:
        if b.start==body.start and b.end==body.end:return batch_view(db,b,True)
        if b.start<=body.end and body.start<=b.end:raise HTTPException(409,"范围与已有批次重叠，请打开已有批次")
        if b.verified_text is None and not reviewed_batch(latest_job(db,b)):raise HTTPException(409,"请先完成此资料的上一批核对")
    b=WorkBatch(id=str(uuid4()),material_id=m.id,start=body.start,end=body.end,units=[],created_at=now(),updated_at=now());db.add(b);s.updated_at=now();db.commit()
    return batch_view(db,b,True)
@router.get("/{ident}/batches/{bid}")
def read_batch(ident:str,bid:str,db:Session=Depends(get_db)):
    return batch_view(db,batch(db,workspace(db,ident),bid),True)
@router.post("/{ident}/batches/{bid}/step",dependencies=[Depends(require_origin)])
def step(ident:str,bid:str,db:Session=Depends(get_db),user:User=Depends(current_user),model:str|None=None,effort:str|None=None,manual_review:bool=False):
    s=workspace(db,ident,True);b=batch(db,s,bid,True);m=db.get(WorkMaterial,b.material_id);f=file_for(db,m,True)
    if b.verified_text is not None:return batch_view(db,b,True)
    existing={u["unit"]:u for u in b.units}
    n=next((n for n in range(b.start,b.end+1) if existing.get(n,{}).get("state")!="done"),None)
    if n is None:return batch_view(db,b,True)
    previous=existing.get(n,{})
    if manual_review and (f.media_type!=imp.DOCX or previous.get("state")!="failed" or not previous.get("image_current")):
        raise HTTPException(409,"当前没有可标记为人工核对的失败图片")
    try:
        if f.media_type==imp.DOCX:
            u=vision.word_step(f,n,previous,model or "Auto",effort,manual_review)
            existing[n]=u;b.units=sorted(existing.values(),key=lambda x:x["unit"]);b.updated_at=now();s.updated_at=now();db.commit()
            return batch_view(db,b,True)
        if f.media_type in storage.IMAGE_TYPES or f.media_type=="application/pdf":
            result=vision.recognize(f,n,model or "Auto",effort)
        else:result=imp.extract(f,"text",n,n)
        u={"unit":n,"state":"done","text":result["text"],"method":result["method"],"warnings":result.get("warnings",[])}
    except HTTPException as exc:
        if vision.model_busy(exc):
            return batch_view(db,b,True)
        u={**previous,"unit":n,"state":"failed","attempts":previous.get("attempts",0)+1,"error":str(exc.detail)[:400]}
    existing[n]=u;b.units=sorted(existing.values(),key=lambda x:x["unit"]);b.updated_at=now();s.updated_at=now();db.commit()
    return batch_view(db,b,True)
@router.post("/{ident}/batches/{bid}/verify",dependencies=[Depends(require_origin)])
def verify(ident:str,bid:str,body:Verify,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True);b=batch(db,s,bid,True)
    if b.verified_text is not None:
        if b.verified_text!=body.text:raise HTTPException(409,"此批已核对，不可覆盖")
        return batch_view(db,b,True)
    if {u["unit"] for u in b.units if u["state"]=="done"}!=set(range(b.start,b.end+1)) or not body.text.strip():raise HTTPException(409,"请先识别完整批次")
    m=db.get(WorkMaterial,b.material_id);file_for(db,m,True);warnings=sorted({w for u in b.units for w in u.get("warnings",[])})
    record=IntakeImport(id=str(uuid4()),file_id=m.file_id,text=body.text,metadata_json={"method":"work_batch","start":b.start,"end":b.end,"total_units":m.total_units,"warnings":warnings},created_at=now());db.add(record);db.flush()
    b.verified_text=body.text;b.import_id=record.id;b.updated_at=now();s.updated_at=now();audit(db,"work.verify",user.id);db.commit()
    return batch_view(db,b,True)
@router.post("/{ident}/batches/{bid}/organize",dependencies=[Depends(require_origin)])
def organize(ident:str,bid:str,body:Organize,db:Session=Depends(get_db),user:User=Depends(current_user)):
    s=workspace(db,ident,True);b=batch(db,s,bid,True)
    if b.job_id:return ai.view(latest_job(db,b),True)
    if not b.verified_text or not b.import_id:raise HTTPException(409,"请先核对识别原文")
    m=db.get(WorkMaterial,b.material_id);f=file_for(db,m,True)
    start=ai.Start(title=(f.name+" · "+str(b.start)+"–"+str(b.end))[:200],subject=body.subject,text=b.verified_text,model=body.model,effort=body.effort,source_id=body.source_id,import_id=b.import_id,import_reviewed=True,intent=body.intent)
    provenance={**ai.build_provenance(db,start),"workspace_id":m.session_id,"work_batch_id":b.id,"work_material_id":m.id,"file_media_type":f.media_type,"reviewed_uids":[]}
    s.updated_at=now()
    return ai.launch(db,user,start,provenance,work_batch=b)
def organize_unverified(ident,bid,body,db,user):
    """Create a draft from a complete machine transcription. Never assert human verification."""
    s=workspace(db,ident,True);b=batch(db,s,bid,True)
    if b.job_id:return ai.view(latest_job(db,b),True)
    if b.verified_text is not None:return organize(ident,bid,body,db,user)
    if {u["unit"] for u in b.units if u.get("state")=="done"}!=set(range(b.start,b.end+1)):
        raise HTTPException(409,"请先完成本批识别")
    m=db.get(WorkMaterial,b.material_id);f=file_for(db,m,True)
    raw="\n\n".join("【原文位置 "+str(u["unit"])+"】\n"+u.get("text","") for u in sorted(b.units,key=lambda x:x["unit"]))
    if not any((u.get("text") or "").strip() for u in b.units) or len(raw)>24000:raise HTTPException(422,"原文过长或为空，请缩小批次")
    warnings=sorted({w for u in b.units for w in u.get("warnings",[])})
    metadata={"method":"work_batch","start":b.start,"end":b.end,"total_units":m.total_units,"warnings":warnings}
    record=IntakeImport(id=str(uuid4()),file_id=f.id,text=raw,metadata_json=metadata,created_at=now());db.add(record);db.flush()
    b.import_id=record.id;s.updated_at=now()
    draft=ai.Start(title=(f.name+" · "+str(b.start)+"–"+str(b.end))[:200],subject=body.subject,text=raw,model=body.model,effort=body.effort,source_id=body.source_id,intent=body.intent)
    provenance={"kind":"file_import","intent":body.intent,"import_id":record.id,"file_id":f.id,"file_name":f.name,"sha256":f.sha256,"edited":False,"import_reviewed":False,**metadata,"workspace_id":m.session_id,"work_batch_id":b.id,"work_material_id":m.id,"file_media_type":f.media_type,"reviewed_uids":[],"single_review":True}
    return ai.launch(db,user,draft,provenance,work_batch=b)

@router.post("/{ident}/batches/{bid}/draft",dependencies=[Depends(require_origin)])
def draft_batch(ident:str,bid:str,body:Organize,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return organize_unverified(ident,bid,body,db,user)

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

@router.get("/{ident}/materials/{mid}/word-block")
def word_block(ident:str,mid:str,unit:int=Query(ge=1,le=10000),db:Session=Depends(get_db)):
    m=material(db,workspace(db,ident),mid);f=file_for(db,m)
    if f.media_type!=imp.DOCX:raise HTTPException(415,"仅Word支持段落原文预览")
    images=[]
    def marker(index,media,loader):
        if media:images.append({"index":index,"media_type":media})
        return f"[Word原图{index}]" if media else f"[Word图片{index}待核对]"
    result=word_images.scan(storage.file_path(f),unit,marker)
    return {**result,"images":images}

@router.get("/{ident}/materials/{mid}/word-image")
def word_image(ident:str,mid:str,unit:int=Query(ge=1,le=10000),index:int=Query(ge=1),db:Session=Depends(get_db)):
    m=material(db,workspace(db,ident),mid);f=file_for(db,m)
    if f.media_type!=imp.DOCX:raise HTTPException(415,"仅Word支持内嵌图片预览")
    selected=None
    def marker(i,media,loader):
        nonlocal selected
        if i==index:selected=loader()
        return f"[Word原图{i}]"
    word_images.scan(storage.file_path(f),unit,marker)
    if selected is None:raise HTTPException(404,"原图不可用，请下载原文件核对")
    return Response(selected[1],media_type=selected[0],headers={"Content-Security-Policy":"sandbox; default-src 'none'","Cache-Control":"private, no-store"})

router.include_router(agent.router)
