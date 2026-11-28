"""Native work entry and compatibility views for historical business records."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, now, audit
from app.models import WorkMaterial, StoredFile, User
from app.api import qoder
from app.services.recognition_plan import propose_range

router=APIRouter()
class Start(BaseModel):
    instruction:str=Field(min_length=1,max_length=2000)
    model:str=Field(default="Auto",max_length=80,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
    effort:str|None=Field(default=None,max_length=16)
    selected_id:str|None=Field(default=None,max_length=36)
    auto:bool=True
    single_review:bool=False
    priority:Literal["normal","high"]="normal"
    chat_session_id:str|None=Field(default=None,max_length=36)
class Confirm(BaseModel):
    plan_id:str=Field(min_length=1,max_length=36)
class Intent(BaseModel):
    model_config=ConfigDict(extra="forbid")
    action:Literal["recognize","open_batch","organize","review","attach","clarify"]
    file_id:str|None=Field(default=None,max_length=36)
    batch_id:str|None=Field(default=None,max_length=36)
    start:StrictInt|None=Field(default=None,ge=1,le=10000)
    count:StrictInt|None=Field(default=None,ge=1,le=10)
    reference_ids:list[str]=Field(default_factory=list,max_length=10)
    match_fields:list[Literal['answer','solution','analysis','proof']]=Field(default_factory=list,max_length=4)
    focus:Literal["mixed","question","knowledge","document"]="mixed"
    goal:Literal["recognition","review","document"]="recognition"
    explanation:str=Field(default="",max_length=500)
    @model_validator(mode="after")
    def validate_action(self):
        if self.action=="clarify":
            if self.file_id or self.batch_id or self.reference_ids or self.start is not None or self.count is not None or not self.explanation.strip():raise ValueError("invalid clarification")
        elif not self.file_id:raise ValueError("missing file")
        if self.action=="recognize":
            if self.batch_id or self.count is None:raise ValueError("missing range")
            if self.start is not None and self.start+self.count-1>10000:raise ValueError("range out of bounds")
        elif self.start is not None or self.count is not None:raise ValueError("unexpected range")
        if self.action in ("open_batch","organize","review") and not self.batch_id:raise ValueError("missing batch")
        if self.action=="attach" and self.batch_id:raise ValueError("unexpected batch")
        if len(set(self.reference_ids))!=len(self.reference_ids) or self.file_id in self.reference_ids:raise ValueError("invalid references")
        if len(set(self.match_fields))!=len(self.match_fields):raise ValueError("duplicate match fields")
        if self.match_fields and (not self.reference_ids or self.goal=="recognition" or self.action in ("attach","clarify")):raise ValueError("matching requires reference files and a review or document goal")
        return self
def current(s):return (s.agent_history or [])[-1] if s.agent_history else None
def save(db,s,r):
    s.agent_history=[*[x for x in (s.agent_history or []) if x["id"]!=r["id"]],r][-12:]
    s.updated_at=now()
def public(r):return {k:v for k,v in r.items() if k not in {"allowed_files","prompt","actor_id","model_job","attempts","phase_at","preference_snapshot","initial_context","linked_chat","native_system","native_prompt","native_resume","native_amendment_count","native_restart","native_receipts","native_interrupt_requested"}} if r else None

def workflow(db,s,r):
    """Derive progress from real extraction, review and registration records.
    Never advance merely because the model described a later stage."""
    from app.api import workspaces as w
    from app.models import WorkBatch
    p=r.get("plan") or {};result=r.get("result") or {}
    if r["state"]!="dispatched":return None
    m=db.get(WorkMaterial,result.get("material_id")) if result.get("material_id") else None
    if not m or m.session_id!=s.id:return {"stage":"unavailable","detail":"资料关联不可用"}
    f=db.get(StoredFile,m.file_id)
    refs=[]
    for ref in p.get("references",[]):
        source=db.get(StoredFile,ref["id"])
        ready=bool(source and not source.archived and any(b.verified_text is not None for b in w.file_batches(db,source.id)))
        refs.append({**ref,"ready":ready,"available":bool(source and not source.archived)})
    out={"material_id":m.id,"goal":p.get("goal","recognition"),"references":refs}
    if not result.get("batch_id"):return {**out,"stage":"attached","detail":"资料已关联"}
    b=db.get(WorkBatch,result["batch_id"])
    owner=db.get(WorkMaterial,b.material_id) if b else None
    if not b or not owner or owner.file_id!=m.file_id:return {**out,"stage":"unavailable","detail":"识别批次不可用"}
    j=w.latest_job(db,b)
    count=sum(1 for u in b.units if u.get("state")=="done")
    out.update(batch_id=b.id,start=b.start,end=b.end,recognized=count,total=b.end-b.start+1,verified=b.verified_text is not None)
    if j:
        out.update(job_id=j.id,job_state=j.state,document_id=j.document_id,reviewed=len((j.provenance or {}).get("reviewed_uids",[])),item_count=len(j.items or []))
        if j.state=="converted":
            stage="registered" if w.registered(db,j) else "document"
            return {**out,"stage":stage,"detail":"已正式入库" if stage=="registered" else "录入文档已生成，尚待正式登记"}
        if j.state=="review":return {**out,"stage":"review","detail":"AI整理已完成，待人工逐条审核"}
        if j.state in ("failed","stopped"):return {**out,"stage":"review_failed","detail":j.detail or "整理已停止或失败"}
        return {**out,"stage":"organizing","detail":"等待AI整理结果，请打开任务查看实时进度"}
    if not f or f.archived:return {**out,"stage":"unavailable","detail":"原件已清理，不能继续识别或整理"}
    if b.verified_text is not None:
        if out["goal"] in ("review","document"):return {**out,"stage":"organize","detail":"原文已核对，可以按计划继续AI整理"}
        return {**out,"stage":"recognized","detail":"本批识别及核对完成；等待新指令"}
    pending=next((u for u in b.units if u.get("state") in ("partial","failed") and "image_total" in u),None)
    if pending:
        out.update(image_unit=pending["unit"],image_total=pending["image_total"],image_completed=pending.get("image_completed",0),image_review=pending.get("image_review",0),image_current=pending.get("image_current"))
    if any(u.get("state")=="failed" for u in b.units):
        if r.get("auto") and not pending and all(u.get("attempts",0)<2 for u in b.units if u.get("state")=="failed"):
            return {**out,"stage":"recognizing","detail":"AI视觉识别失败，正在自动重试原图"}
        return {**out,"stage":"recognition_failed","detail":"AI识别失败，可继续本批；未使用普通OCR"}
    if pending:return {**out,"stage":"recognizing","detail":"正在逐张识别Word内嵌图片，已保存完成进度"}
    if count==out["total"]:
        if r.get("single_review") and r.get("auto") and out["goal"] in ("review","document"):return {**out,"stage":"organize","detail":"原文识别完成，正在准备逐题审核草稿"}
        return {**out,"stage":"verify","detail":"本批原文已提取，等待人工核对"}
    return {**out,"stage":"recognizing","detail":"本批尚未识别完成，可继续本批"}

def present(db,s,r):
    data=public(r)
    if data and data["state"]=="dispatched":data["workflow"]=workflow(db,s,r)
    return data
def resolve(db,i):
    from app.api import workspaces as w
    if i.action=="clarify":return {"action":"clarify","explanation":i.explanation}
    f=db.scalar(w.original_query().where(StoredFile.id==i.file_id,StoredFile.archived==False))
    if not f:raise HTTPException(409,"原始资料不可用")
    refs=[]
    for fid in i.reference_ids:
        ref=db.scalar(w.original_query().where(StoredFile.id==fid,StoredFile.archived==False))
        if not ref:raise HTTPException(409,"参考资料不可用")
        refs.append({"id":ref.id,"name":ref.name})
    p=w.library_row(db,f);bs=w.file_batches(db,f.id)
    unit="页" if f.media_type=="application/pdf" else "段" if f.media_type==w.imp.DOCX else "份"
    result={"action":i.action,"file_id":f.id,"file_name":f.name,"focus":i.focus,"goal":i.goal,"match_fields":i.match_fields,"references":refs,"explanation":i.explanation,"unit":unit,"verified_units":p["verified_units"]}
    if i.action=="recognize":
        if i.count>(10 if unit!="份" else 1):raise HTTPException(422,"识别范围不适用")
        total=p["total_units"] if p["total_units"] is not None else w.unit_count(f)
        result.update(propose_range({"start":i.start,"count":i.count},bs,total,p["next_unit"]))
        if result.get("blocked"):raise HTTPException(409,result["note"])
        if result.get("batch_id"):result["action"]="open_batch"
    elif i.batch_id:
        b=next((x for x in bs if x.id==i.batch_id),None)
        if not b:raise HTTPException(409,"批次不属于该资料")
        j=w.latest_job(db,b)
        result.update(batch_id=b.id,start=b.start,end=b.end)
        if i.action=="organize" and not b.verified_text:raise HTTPException(409,"原文尚未核对")
        if i.action=="review" and not j:raise HTTPException(409,"该批尚未整理")
        if j:result["job_id"]=j.id
    return result
@router.get("/{ident}/agent/history")
def history(ident:str,db:Session=Depends(get_db)):
    from app.api import workspaces as w
    s=w.workspace(db,ident)
    return [public(r) for r in (s.agent_history or [])]

@router.get("/{ident}/agent")
def status(ident:str,db:Session=Depends(get_db)):
    from app.api import workspaces as w
    s=w.workspace(db,ident,True);r=current(s)
    if r and not r.get("native") and r.get("state") in ("running","ready","confirmed"):
        from app.core.ai_work import retire_old
        r=retire_old(db,s,dict(r))
    return present(db,s,r)
@router.post("/{ident}/agent",dependencies=[Depends(require_origin)])
def start(ident:str,body:Start,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from app.api import workspaces as w
    s=w.workspace(db,ident,True)
    if not body.instruction.strip():raise HTTPException(422,"请输入工作要求")
    previous=current(s)
    if previous and not previous.get("native") and previous.get("state") in ("running","ready","confirmed"):
        from app.core.ai_work import retire_old
        previous=retire_old(db,s,dict(previous))
    if previous and previous.get("native") and previous["state"]=="running":
        from app.core.ai_work import revise
        return revise(db,s,dict(previous),body,user)
    if previous and (previous["state"] in ("running","ready","confirmed") or previous.get("phase")=="executing" and previous["state"]=="cancelled"):
        raise HTTPException(409,"已有工作正在执行，请先停止或等待当前步骤结束")
    if previous and previous.get("auto") and previous["state"]=="dispatched":
        progress=workflow(db,s,previous)
        if progress and progress["stage"]=="organizing":
            raise HTTPException(409,"此前提交的实际资料整理任务仍在运行，请先核对或停止该任务")
    from app.core.native_work import begin
    return begin(db,s,body,user)
@router.post("/{ident}/agent/cancel",dependencies=[Depends(require_origin)])
def cancel(ident:str,body:Confirm,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from app.api import workspaces as w
    s=w.workspace(db,ident,True);r=current(s)
    if not r or r["id"]!=body.plan_id or r["state"] not in ("running","ready","clarify","confirmed","dispatched"):raise HTTPException(409,"计划已变化")
    if r["state"]=="running" and (not r.get("auto") or r.get("phase") in ("pending","model")):
        try:qoder.request("POST","/chat/"+r.get("model_job",r["id"])+"/cancel",{})
        except HTTPException as e:
            if e.status_code!=404:raise
    child=r.get("child")
    detail="已停止后续执行；保留已完成成果"
    if r.get("native"):
        from app.core.native_work import video_waiting
        from app.api import video
        for entry in video_waiting(r):
            item=entry["video_child"]
            try:
                video.job_action(item["project"],item["id"],"cancel",db)
                entry["detail"]="已请求停止原视频任务"
            except HTTPException:entry["detail"]="未确认停止；请到视频模块核对"
        if video_waiting(r):detail+="；已尝试停止关联视频任务"
    if r["state"]=="running" and r.get("phase")=="business" and child:
        try:
            from app.api import video,intelligence
            if child["kind"]=="video":video.job_action(child["project"],child["id"],"cancel",db)
            else:intelligence.stop(child["id"],db)
            detail+="；已提交当前业务任务停止请求"
        except HTTPException:
            detail+="；业务任务未确认停止，请在对应模块查看"
    r={**r,"state":"cancelled","detail":detail};save(db,s,r);audit(db,"work.agent.cancel",user.id);db.commit();return public(r)
@router.post("/{ident}/agent/retry",dependencies=[Depends(require_origin)])
def retry(ident:str,body:Confirm,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from app.api import workspaces as w
    from app.core.ai_work import MAX_TOTAL_STEPS
    s=w.workspace(db,ident,True);r=current(s)
    if not r or r["id"]!=body.plan_id or not r.get("auto") or r["state"]!="failed":
        raise HTTPException(409,"仅失败的自动工作支持继续")
    if r.get("actor_id")!=user.id:raise HTTPException(403,"无权操作")
    if r.get("phase")=="executing":raise HTTPException(409,"上次写入结果不明确，请先在业务模块核对")
    r=dict(r)
    if len(r.get("steps",[]))>=MAX_TOTAL_STEPS:raise HTTPException(409,"当前工作已达总安全步骤上限，请另开工作并引用历史成果")
    r["stage_start"]=len(r.get("steps",[]))
    if not r.get("native"):raise HTTPException(409,"旧AI执行器已移除；请核对已完成成果并直接提出新的工作要求")
    from app.core.native_work import retry as native_retry
    return native_retry(db,s,r,user)

@router.post("/{ident}/agent/confirm",dependencies=[Depends(require_origin)])
def confirm(ident:str,body:Confirm,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from app.api import workspaces as w
    s=w.workspace(db,ident,True);r=current(s)
    if not r or r["id"]!=body.plan_id or r["state"] not in ("ready","confirmed"):raise HTTPException(409,"计划已变化")
    if r["state"]=="ready":
        expected=dict(r["plan"])
        if expected.get("action")!="clarify":
            expected.setdefault("goal","recognition");expected.setdefault("match_fields",[])
        if resolve(db,Intent.model_validate(r["intent"]))!=expected:raise HTTPException(409,"资料或进度已变化，请重新规划")
    if r["state"]=="ready":
        r={**r,"state":"confirmed","detail":"计划已确认，尚未执行"};save(db,s,r);audit(db,"work.agent.confirm",user.id);db.commit()
    return public(r)


@router.post("/{ident}/agent/dispatch",dependencies=[Depends(require_origin)])
def dispatch(ident:str,body:Confirm,db:Session=Depends(get_db),user:User=Depends(current_user)):
    """Idempotent dispatch of an explicitly confirmed plan, using the existing guarded tools.
    The exact range is frozen at confirmation, not recomputed during recovery.
    Recognition itself still proceeds page by page and pauses for review.
    """
    from app.api import workspaces as w
    s=w.workspace(db,ident,True);r=current(s)
    if not r or r["id"]!=body.plan_id or r["state"] not in ("confirmed","dispatched"):
        raise HTTPException(409,"请先确认当前计划")
    if r["state"]=="dispatched":return present(db,s,r)
    p=r["plan"];intent=Intent.model_validate(r["intent"])
    if p["action"]=="clarify":raise HTTPException(422,"澄清不是执行操作")
    # Recheck all originals before attaching, including previously attached files.
    ids=sorted(set([intent.file_id,*intent.reference_ids]))
    originals=list(db.scalars(w.original_query().where(StoredFile.id.in_(ids),StoredFile.archived==False)))
    if len(originals)!=len(ids):raise HTTPException(409,"原件已不可用，请重新规划")
    # Existing tools commit independently. Exact range creation and organization are idempotent.
    linked=w.attach(ident,w.Attach(file_ids=ids),db,user)
    m=next((x for x in linked["materials"] if x["file"]["id"]==intent.file_id),None)
    if not m or m["file"].get("archived"):raise HTTPException(409,"资料不可用")
    result={"material_id":m["id"],"action":p["action"]}
    if p["action"]=="recognize":
        b=w.create_batch(ident,m["id"],w.Range(start=p["start"],end=p["end"]),db,user)
        result["batch_id"]=b["id"]
    elif p["action"]!="attach":
        b=w.read_batch(ident,p["batch_id"],db)
        result["batch_id"]=b["id"]
        if p["action"]=="organize":
            job=w.organize(ident,b["id"],w.Organize(model=r["model"],effort=r["effort"],intent=p["focus"]),db,user)
            result["job_id"]=job["id"]
        elif p["action"]=="review":
            if not b["job_id"]:raise HTTPException(409,"该批尚无整理任务")
            result["job_id"]=b["job_id"]
    # Another tab may have created a newer plan while these guarded tools committed.
    s=w.workspace(db,ident,True)
    latest=current(s)
    if latest and latest["id"]==r["id"]:
        if latest["state"]=="dispatched":return present(db,s,latest)
        r={**latest,"state":"dispatched","result":result,"detail":"已进入对应工作流程，结果仍需核对"}
        save(db,s,r);audit(db,"work.agent.dispatch",user.id);db.commit()
        return present(db,s,r)
    # Do not move an older record to the end or overwrite the new current plan.
    r={**r,"state":"dispatched","result":result,"detail":"已进入对应工作流程"}
    s.agent_history=[r if x["id"]==r["id"] else x for x in (s.agent_history or [])]
    audit(db,"work.agent.dispatch",user.id);db.commit()
    return present(db,s,r)

@router.post("/{ident}/agent/advance",dependencies=[Depends(require_origin)])
def advance(ident:str,body:Confirm,db:Session=Depends(get_db),user:User=Depends(current_user)):
    """Resume only the confirmed batch, never start another batch or approve review."""
    from app.api import workspaces as w
    s=w.workspace(db,ident,True);r=current(s)
    if not r or r["id"]!=body.plan_id or r["state"]!="dispatched":raise HTTPException(409,"当前工作计划已变化")
    stage=workflow(db,s,r)
    if not stage:raise HTTPException(409,"没有可继续的工作")
    if stage.get("job_id"):return present(db,s,r)
    if stage["stage"]!="organize":raise HTTPException(409,"必须先核对原文且计划明确要求继续整理")
    plan=r["plan"]
    organize=w.organize_unverified if r.get("single_review") and not stage.get("verified") else w.organize
    job=organize(ident,stage["batch_id"],w.Organize(model=r["model"],effort=r["effort"],intent=plan["focus"]),db,user)
    s=w.workspace(db,ident,True);latest=current(s)
    if latest and latest["id"]==r["id"]:
        r={**latest,"result":{**latest["result"],"job_id":job["id"]},"detail":"已进入AI整理，等待审核"}
        save(db,s,r)
    else:
        r={**r,"result":{**r["result"],"job_id":job["id"]},"detail":"已进入AI整理，等待审核"}
        s.agent_history=[r if x["id"]==r["id"] else x for x in (s.agent_history or [])]
    audit(db,"work.agent.advance",user.id);db.commit()
    return present(db,s,r)

class MatchAdvance(Confirm):
    job_id:str=Field(min_length=1,max_length=36)
    source_batch_id:str=Field(min_length=1,max_length=36)
    revision:StrictInt=Field(ge=1)

def missing_match_items(items,fields,attempts):
    """Do not silently repeat attempts on an unchanged target and reference batch.
    Failed/discarded proposals remain retryable via the explicit manual matching tool."""
    from app.api import intelligence as ai
    eligible=[]
    for item in items:
        if item.get("reuse_resource_id"):continue
        missing=[k for k in fields if k in ai.allowed_supplements(item)]
        if not missing:continue
        # A previous attempt counts only for the same item and all requested missing fields.
        attempted=set()
        for snap,previous_fields in attempts.get(item["uid"],[]):
            if snap.get("content")==item.get("content") and snap.get("title")==item.get("title"):
                attempted.update(previous_fields)
        if set(missing)<=attempted:continue
        eligible.append({"uid":item["uid"],"title":item.get("title") or item.get("content","")[:100],"fields":missing})
    return eligible

def matching_context(db,s,r,job_id):
    from app.api import workspaces as w
    from app.models import IntakeJob, IntakeSupplement
    p=r.get("plan") or {};fields=p.get("match_fields",[])
    if r["state"]!="dispatched" or not fields:return None
    stage=workflow(db,s,r)
    if not stage or stage.get("job_id")!=job_id:return None
    j=db.get(IntakeJob,job_id)
    if not j or j.state!="review":return None
    groups=list(db.scalars(select(IntakeSupplement).where(IntakeSupplement.job_id==j.id)))
    pending=any(x.state in ("running","review") for x in groups)
    candidates=[]
    unavailable=[]
    for ref in p.get("references",[]):
        f=db.get(StoredFile,ref["id"])
        if not f or f.archived:
            unavailable.append({**ref,"reason":"原件不可用"});continue
        batches=[b for b in w.file_batches(db,f.id) if b.verified_text]
        if not batches:
            unavailable.append({**ref,"reason":"尚无已核对的参考批次"});continue
        for b in batches:
            attempts={}
            for row in groups:
                snap=row.base_item or {};meta=snap.get("_wg_source") or {}
                if meta.get("batch_id")!=b.id:continue
                # Running group snapshots contain all targeted entries; finished rows contain one.
                entries=snap.get("_wg_source_targets") or [{"item":snap,"fields":row.fields}]
                for e in entries:
                    item=e.get("item") or {}
                    attempts.setdefault(item.get("uid"),[]).append((item,e.get("fields") or []))
            targets=missing_match_items(j.items,fields,attempts)
            candidates.append({"batch_id":b.id,"file_id":f.id,"file_name":f.name,"start":b.start,"end":b.end,"eligible_count":len(targets),"targets":targets[:10]})
    return {"plan_id":r["id"],"job_id":j.id,"revision":j.revision,"fields":fields,"pending":pending,"candidates":candidates,"unavailable":unavailable}

@router.get("/{ident}/agent/matching")
def planned_matching(ident:str,job_id:str,db:Session=Depends(get_db)):
    from app.api import workspaces as w
    s=w.workspace(db,ident);r=current(s)
    return matching_context(db,s,r,job_id) if r else None

@router.post("/{ident}/agent/matching",dependencies=[Depends(require_origin)])
def execute_matching(ident:str,body:MatchAdvance,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from app.api import workspaces as w, intelligence as ai
    s=w.workspace(db,ident,True);r=current(s)
    if not r or r["id"]!=body.plan_id or r["state"]!="dispatched":raise HTTPException(409,"工作计划已变化")
    # Lock the job before deriving candidates; existing matching tool reuses that lock.
    j=ai.get_job(db,body.job_id)
    context=matching_context(db,s,r,j.id)
    if not context or context["revision"]!=body.revision:raise HTTPException(409,"审核草稿或计划已变化，请刷新")
    if context["pending"]:raise HTTPException(409,"请先处理当前匹配建议")
    candidate=next((x for x in context["candidates"] if x["batch_id"]==body.source_batch_id),None)
    if not candidate or not candidate["targets"]:raise HTTPException(409,"参考批次不属于计划或没有新的待匹配条目")
    payload=ai.BatchSourceStart(revision=j.revision,item_uids=[t["uid"] for t in candidate["targets"]],fields=context["fields"],source_batch_id=candidate["batch_id"],instruction="按照原工作计划匹配缺失字段；不得生成或改写。"+r["instruction"][:1800])
    return ai.source_match_batch(j.id,payload,db,user)
