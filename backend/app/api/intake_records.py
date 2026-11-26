"""Unified, read-only intake index. Only explicit persisted relations merge records."""
import json
from collections import defaultdict
from typing import Literal
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, audit
from app.models import WorkSession, WorkMaterial, WorkBatch, StoredFile, IntakeJob, TeachingDocument, TeachingResource, Setting, User
from app.api import resources as bank

router=APIRouter(prefix="/intake-records",dependencies=[Depends(current_user)])
STATUSES=("intaking","recognizing","verify","organizing","review","register","registered","failed")
TYPES={"exam","textbook","handout","other"}
PREFIX="intake.record."
PRIORITY={"review":0,"verify":1,"failed":2,"organizing":3,"recognizing":4,"register":5,"intaking":6,"registered":7}

def url(path,**params):
    return path+"?"+urlencode(params)

def document_info(d):
    counts={k:sum(b.get("kind")==k or b.get("kind")=="reference" and (b.get("snapshot") or {}).get("kind")==k for b in d.blocks) for k in ("question","knowledge")}
    pending=any(b.get("kind") in ("question","knowledge") or b.get("edit_reference_revision") for b in d.blocks)
    return counts,pending

def build_records(db):
    # Select only the fields needed by the index, never original file contents or job input text.
    sessions=list(db.execute(select(WorkSession.id,WorkSession.title,WorkSession.created_at,WorkSession.updated_at,WorkSession.agent_history)))
    materials=list(db.execute(select(WorkMaterial.id,WorkMaterial.session_id,WorkMaterial.file_id,WorkMaterial.total_units,StoredFile.name,StoredFile.media_type,StoredFile.archived).join(StoredFile,StoredFile.id==WorkMaterial.file_id)))
    batches=list(db.execute(select(WorkBatch.id,WorkBatch.material_id,WorkBatch.start,WorkBatch.end,WorkBatch.units,(WorkBatch.verified_text.is_not(None)).label("verified"),WorkBatch.job_id,WorkBatch.created_at,WorkBatch.updated_at)))
    jobs=list(db.execute(select(IntakeJob.id,IntakeJob.title,IntakeJob.state,IntakeJob.document_id,IntakeJob.retry_of,IntakeJob.provenance,IntakeJob.source_id,IntakeJob.items,IntakeJob.created_at,IntakeJob.updated_at)))
    docs=list(db.execute(select(TeachingDocument.id,TeachingDocument.title,TeachingDocument.source_id,TeachingDocument.blocks,TeachingDocument.revision,TeachingDocument.created_at,TeachingDocument.updated_at).where(TeachingDocument.kind=="intake",TeachingDocument.archived==False)))
    sources=dict(db.execute(select(TeachingResource.id,TeachingResource.source_type).where(TeachingResource.kind=="source")).all())
    names=dict(db.execute(select(StoredFile.id,StoredFile.name)).all())
    parents={}
    def node(prefix,ident):
        key=prefix+":"+ident;parents.setdefault(key,key);return key
    def root(k):
        while parents[k]!=k:
            parents[k]=parents[parents[k]];k=parents[k]
        return k
    def join(a,b):
        a,b=root(a),root(b)
        if a!=b:parents[b]=a
    sm={s.id:s for s in sessions};mm={m.id:m for m in materials};jm={j.id:j for j in jobs};dm={d.id:d for d in docs}
    bm={b.id:b for b in batches};successors={j.retry_of:j.id for j in jobs if j.retry_of}
    for s in sessions:node("w",s.id)
    for d in docs:node("d",d.id)
    for j in jobs:
        key=node("j",j.id);p=j.provenance or {}
        if j.retry_of in jm:join(key,node("j",j.retry_of))
        if j.document_id in dm:join(key,node("d",j.document_id))
        wid=p.get("workspace_id")
        if wid in sm:join(key,node("w",wid))
        b=bm.get(p.get("work_batch_id"))
        if b and b.material_id in mm:join(key,node("w",mm[b.material_id].session_id))
    for b in batches:
        if b.job_id in jm and b.material_id in mm:join(node("j",b.job_id),node("w",mm[b.material_id].session_id))
    groups=defaultdict(lambda:{"w":[],"j":[],"d":[]})
    for k in parents:
        prefix,ident=k.split(":",1);groups[root(k)][prefix].append({"w":sm,"j":jm,"d":dm}[prefix][ident])
    mats_by_session=defaultdict(list);batches_by_file=defaultdict(list)
    for m in materials:mats_by_session[m.session_id].append(m)
    for b in batches:
        if b.material_id in mm:batches_by_file[mm[b.material_id].file_id].append(b)
    from app.api import workspaces as work
    all_file_batches=work.batch_groups(db,batches_by_file)
    all_states=work.batch_states(db,[b for bs in all_file_batches.values() for b in bs])
    result=[]
    for group in groups.values():
        ws,js,ds=group["w"],group["j"],group["d"]
        current=[j for j in js if j.id not in successors]
        # Stable identity uses oldest related work or root job, not mutable name/source label.
        anchor=min(ws or js or ds,key=lambda x:(x.created_at,x.id))
        key=("w:" if ws else "j:" if js else "d:")+anchor.id
        latest=max(ws or ds or current,key=lambda x:(x.updated_at,x.id))
        title=latest.title
        source_ids={x.source_id for x in [*js,*ds] if x.source_id}
        source_types={sources.get(s) for s in source_ids}&TYPES
        source_type=next(iter(source_types)) if len(source_types)==1 else "uncategorized"
        method="ai" if ws or js else "manual"
        # A document with blocks not produced by its associated jobs has mixed authorship.
        ai_uids={b.get("uid") for j in js for b in (j.items or [])}
        if js and any(any(b.get("kind") in ("question","knowledge","reference") and b.get("uid") not in ai_uids for b in d.blocks) for d in ds):method="mixed"
        actions=[];file_names=set();progress=[];active_files={}
        def action(state,label,href,updated):
            actions.append({"state":state,"label":label,"href":href,"updated_at":updated})
        for d in ds:
            counts,pending=document_info(d)
            state="register" if pending and js else "intaking" if pending or not sum(counts.values()) else "registered"
            action(state,"继续入库" if state=="register" else "继续录入" if state=="intaking" else "查看资料",url("/intake",doc=d.id),d.updated_at)
            progress.append(str(counts["question"])+" 道题 / "+str(counts["knowledge"])+" 个知识单元")
        for j in current:
            if j.document_id in dm and j.state=="converted":continue
            state={"running":"organizing","review":"review","failed":"failed","stopped":"failed","converted":"failed"}.get(j.state,"intaking")
            params={"job":j.id}
            if state=="review":params["review"]="1"
            wid=(j.provenance or {}).get("workspace_id")
            if wid in sm:params["fromWorkspace"]=wid
            action(state,{"organizing":"查看整理进度","review":"继续审核","failed":"查看任务","intaking":"继续录入"}[state],url("/work",**params),j.updated_at)
            if state=="review":progress.append(str(len((j.provenance or {}).get("reviewed_uids",[])))+"/"+str(len(j.items or []))+" 条已审核")
            f=(j.provenance or {}).get("file_id")
            if f in names:file_names.add(names[f])
        for w in ws:
            related=mats_by_session[w.id]
            # A reference file is not a requirement to finish the main document.
            history=w.agent_history or []
            primary={r.get("plan",{}).get("file_id") for r in history if isinstance(r.get("plan"),dict)}
            refs={f.get("id") for r in history if isinstance(r.get("plan"),dict) for f in r["plan"].get("references",[]) if isinstance(f,dict)}
            primary.update((j.provenance or {}).get("file_id") for j in js)
            for m in related:
                file_names.add(m.name)
                if m.file_id in refs and m.file_id not in primary:continue
                active_files.setdefault(m.file_id,m)
                bs=batches_by_file[m.file_id]
                verified={n for b in bs if b.verified for n in range(b.start,b.end+1)}
                # Completion requires actual document reference/registration evidence below, never just AI conversion.
                for b in bs:
                    if b.verified:continue
                    state="failed" if any(u.get("state")=="failed" for u in b.units) else "verify" if len({u["unit"] for u in b.units if u.get("state")=="done"})==b.end-b.start+1 else "recognizing"
                    action(state,"核对原文" if state=="verify" else "继续识别",url("/work",workspace=w.id,material=m.id,batch=b.id),b.updated_at)
                if not m.archived and (m.total_units is None or len(verified)<m.total_units):
                    action("intaking","继续录入",url("/work",workspace=w.id,material=m.id),w.updated_at)
            if not related:action("intaking","继续工作",url("/work",workspace=w.id),w.updated_at)
        # True registration coverage is computed using the existing bulk status service.
        if active_files:
            for fid,m in active_files.items():
                bs=all_file_batches.get(fid,[]);p=work.progress(db,None,bs,m.total_units,all_states)
                unit="页" if m.media_type=="application/pdf" else "段" if "wordprocessingml" in m.media_type else "份"
                progress.append(m.name+"：已核对 "+str(p["verified_units"])+"/"+(str(m.total_units) if m.total_units is not None else "未知")+unit+"，已入库 "+str(p["registered_units"])+unit)
                for b in bs:
                    if b.verified_text is not None and not b.job_id and not m.archived:
                        action("intaking","继续整理",url("/work",workspace=m.session_id,material=m.id,batch=b.id),b.updated_at)
                if not p["complete"]:
                    # Verified or archived originals may have no pending batch action; do not mark the entire file complete.
                    if not any(a["state"]!="registered" for a in actions):
                        action("intaking","查看资料进度",url("/work",workspace=m.session_id,material=m.id),sm[m.session_id].updated_at)
        if not actions:continue
        actions.sort(key=lambda a:(PRIORITY[a["state"]],-a["updated_at"],a["href"]))
        unique=[];seen=set()
        for a in actions:
            if a["href"] not in seen:unique.append(a);seen.add(a["href"])
        updated=max([x.updated_at for x in [*ws,*js,*ds]]+[a["updated_at"] for a in actions])
        result.append({"id":key,"title":title,"source_type":source_type,"method":method,"status":unique[0]["state"],"href":unique[0]["href"],"action":unique[0]["label"],"actions":unique,"progress":progress,"file_names":sorted(file_names),"created_at":min(x.created_at for x in [*ws,*js,*ds]),"updated_at":updated,"document_id":ds[0].id if method=="manual" and len(ds)==1 else None,"revision":ds[0].revision if method=="manual" and len(ds)==1 else None})
    prefs={}
    for s in db.scalars(select(Setting).where(Setting.key.startswith(PREFIX))):
        try:prefs[s.key[len(PREFIX):]]=json.loads(s.value)
        except (ValueError,TypeError):continue
    for r in result:
        pref=prefs.get(r["id"],{})
        if not isinstance(pref,dict):pref={}
        r["original_title"]=r["title"]
        r["title"]=pref.get("title") or r["title"]
        r["hidden"]=bool(pref.get("hidden"))
    return result

@router.get("")
def listing(q:str=Query("",max_length=200),status:str=Query("",max_length=20),source_type:str=Query("",max_length=20),method:str=Query("",max_length=20),sort:Literal["recent","created","name"]="recent",offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),hidden:bool=False,db:Session=Depends(get_db)):
    if status and status not in STATUSES or source_type and source_type not in TYPES|{"uncategorized"} or method and method not in ("manual","ai","mixed"):raise HTTPException(422,"筛选条件无效")
    needle=q.strip().casefold()
    rows=[r for r in build_records(db) if r["hidden"]==hidden and (not status or status==r["status"]) and (not source_type or source_type==r["source_type"]) and (not method or method==r["method"]) and (not needle or any(needle in v.casefold() for v in [r["title"],r["original_title"],*r["file_names"]]))]
    rows.sort(key=lambda r:(r["title"].casefold(),r["id"]) if sort=="name" else (-r["created_at" if sort=="created" else "updated_at"],r["id"]))
    return {"items":rows[offset:offset+limit],"total":len(rows)}

class Preference(BaseModel):
    title:str|None=Field(default=None,min_length=1,max_length=200)
    hidden:bool|None=None

@router.patch("/{ident}",dependencies=[Depends(require_origin)])
def preference(ident:str,body:Preference,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user)
    r=next((r for r in build_records(db) if r["id"]==ident),None)
    if not r:raise HTTPException(404,"录入记录不存在")
    if body.title is not None and not body.title.strip():raise HTTPException(422,"名称不能为空")
    pref={"title":body.title.strip() if body.title is not None else r["title"],"hidden":body.hidden if body.hidden is not None else r["hidden"]}
    db.merge(Setting(key=PREFIX+ident,value=json.dumps(pref,ensure_ascii=False)))
    audit(db,"intake.record.preference",user.id);db.commit()
    return {"id":ident,**pref}
