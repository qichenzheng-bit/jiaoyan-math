"""Permanent work removal while preserving shared originals and generated documents."""
from fastapi import HTTPException
from sqlalchemy import select, delete
from app.core.security import now
from app.models import IntakeJob, IntakeSupplement, WorkBatch, WorkMaterial, IntakeImport, FileReference, StoredFile
from app.api import qoder

def stop_model(ident, created_at=0):
    try:
        status=qoder.request("GET","/chat/"+ident).get("state")
    except HTTPException as e:
        if e.status_code==404 and now()-created_at>30:return
        raise HTTPException(409,"无法确认当前任务已停止，请稍后重试") from e
    if status in ("running","queued","cancelling"):
        qoder.request("POST","/chat/"+ident+"/cancel",{})
        try:status=qoder.request("GET","/chat/"+ident).get("state")
        except HTTPException as e:
            if e.status_code==404:return
            raise
    if status not in ("done","failed","stopped","cancelled","canceled"):
        raise HTTPException(409,"正在停止当前任务，请稍后重新删除")

def chain(db,ids):
    ids=set(ids)
    while ids:
        rows=list(db.scalars(select(IntakeJob).where(IntakeJob.id.in_(ids)).with_for_update()))
        parents={j.retry_of for j in rows if j.retry_of}
        children=set(db.scalars(select(IntakeJob.id).where(IntakeJob.retry_of.in_(ids))))
        added=(parents|children)-ids
        if not added:return rows
        ids.update(added)
    return []

def unlink(db,kind,ids):
    if ids:db.execute(delete(FileReference).where(FileReference.owner_type==kind,FileReference.owner_id.in_(ids)))

def clean_imports(db,ids):
    for ident in ids:
        if not ident:continue
        if db.scalar(select(WorkBatch.id).where(WorkBatch.import_id==ident).limit(1)):continue
        if db.scalar(select(IntakeJob.id).where(IntakeJob.provenance["import_id"].as_string()==ident).limit(1)):continue
        row=db.get(IntakeImport,ident)
        if row:db.delete(row)

def remove_jobs(db,rows):
    ids={j.id for j in rows}
    if not ids:return set()
    supplements=list(db.scalars(select(IntakeSupplement).where(IntakeSupplement.job_id.in_(ids)).with_for_update()))
    for j in rows:
        if j.state=="running":stop_model(j.id,j.created_at)
    for s in supplements:
        if s.state=="running":stop_model(s.id,s.created_at)
    retained={j.id for j in rows if j.document_id}
    for s in supplements:
        if s.job_id not in retained or s.state!="accepted":
            unlink(db,"intake_supplement",[s.id]);db.delete(s)
    for b in db.scalars(select(WorkBatch).where(WorkBatch.job_id.in_(ids)).with_for_update()):
        related=next((j.id for j in rows if j.id in retained and (j.provenance or {}).get("work_batch_id")==b.id),None)
        if b.job_id not in retained:b.job_id=related
    imports={j.provenance.get("import_id") for j in rows if j.provenance and j.provenance.get("import_id")}
    for j in rows:
        j.retry_of=None
        if j.id in retained:
            j.provenance={**(j.provenance or {}),"history_removed":True}
        else:unlink(db,"intake_job",[j.id])
    db.flush()
    for j in rows:
        if j.id not in retained:db.delete(j)
    db.flush()
    clean_imports(db,imports)
    return ids

def stop_workspace(db,s):
    from app.api import video
    for r in s.agent_history or []:
        state=r.get("state");phase=r.get("phase")
        if phase=="executing" and state in ("running","cancelled"):
            raise HTTPException(409,"当前业务步骤仍在执行，请在步骤结束后删除")
        if state=="running" and (phase=="model" or not r.get("auto")):
            stop_model(r.get("model_job") or r["id"],r.get("phase_at",r.get("created_at",0)))
        child=r.get("child") or {}
        if child.get("kind")=="video" and child.get("id"):
            try:v=video.job_read(child["project"],child["id"],db)
            except HTTPException as e:
                if e.status_code==404:continue
                raise
            if v.get("status") in ("running","queued","cancelling"):
                video.job_action(child["project"],child["id"],"cancel",db)
                v=video.job_read(child["project"],child["id"],db)
                if v.get("status") in ("running","queued","cancelling"):raise HTTPException(409,"视频任务正在停止，请稍后重新删除")

def remove_workspace(db,s):
    stop_workspace(db,s)
    materials=list(db.scalars(select(WorkMaterial).where(WorkMaterial.session_id==s.id).order_by(WorkMaterial.file_id).with_for_update()))
    deleted_batches=[];shared_batch_ids=set();imports=set();roots=set()
    for m in materials:
        db.scalar(select(StoredFile).where(StoredFile.id==m.file_id).with_for_update())
        batches=list(db.scalars(select(WorkBatch).where(WorkBatch.material_id==m.id).with_for_update()))
        other=db.scalar(select(WorkMaterial).where(WorkMaterial.file_id==m.file_id,WorkMaterial.session_id!=s.id).order_by(WorkMaterial.id).limit(1))
        for b in batches:
            if other:
                b.material_id=other.id;shared_batch_ids.add(b.id)
                for j in chain(db,[b.job_id] if b.job_id else []):
                    j.provenance={**(j.provenance or {}),"workspace_id":other.session_id,"work_material_id":other.id}
            else:
                if b.job_id:roots.add(b.job_id)
                if b.import_id:imports.add(b.import_id)
                deleted_batches.append(b)
    for j in db.scalars(select(IntakeJob).where(IntakeJob.provenance["workspace_id"].as_string()==s.id).with_for_update()):
        if (j.provenance or {}).get("work_batch_id") not in shared_batch_ids:roots.add(j.id)
    for r in s.agent_history or []:
        child=r.get("child") or {}
        if child.get("kind")=="intake" and child.get("id"):roots.add(child["id"])
        for step in r.get("steps") or []:
            if step.get("tool")=="intake_text" or step.get("name")=="intake_text":
                result=step.get("result") or {}
                if isinstance(result,dict) and result.get("id"):roots.add(result["id"])
    db.flush()
    rows=[j for j in chain(db,roots) if (j.provenance or {}).get("work_batch_id") not in shared_batch_ids]
    removed=remove_jobs(db,rows)
    for b in deleted_batches:db.delete(b)
    db.flush()
    for m in materials:
        unlink(db,"work_material",[m.id]);db.delete(m)
    db.flush()
    clean_imports(db,imports)
    db.delete(s)
    return sorted(removed)
