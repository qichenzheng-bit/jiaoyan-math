import json
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel,Field
from sqlalchemy import select,func,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.core.db import get_db
from app.core.security import current_user,require_origin,audit,now
from app.core.bank_history import record,history
from app.core.question_structure import resolve,project,digest,Method
from app.core.content_normalization import question_fingerprint
from app.core import method_recommendation as rec
from app.models import TeachingResource as R,ResourceSourceLink as L,ResourceKnowledgeLink as K,KnowledgePointCatalog as P,Setting,User,TeachingDocument
from app.api import resources as bank,documents as docs
from app.services.inline_images import validate_images,protect_resource_images

router=APIRouter(prefix="/bank",tags=["question-bank"],dependencies=[Depends(current_user)])
write=[Depends(require_origin)]
def read_setting(db,key,default=None):
    s=db.get(Setting,key)
    return json.loads(s.value) if s else default
def store(db,key,value):
    db.merge(Setting(key=key,value=json.dumps(value,ensure_ascii=False)))
def question(db,id,revision=None):
    r=bank.existing(db,id,revision is not None)
    if r.kind!="question" or r.archived:raise HTTPException(422,"请选择有效题目")
    if revision is not None and revision!=r.revision:raise HTTPException(409,"题目版本已变化")
    return r
def recommendation_view(db,r):
    return {"revision":r.revision,"groups":bank.recommendation_groups(r),"evaluation":bank.read_recommendation(db,r)}
class MethodChange(BaseModel):
    revision:int=Field(ge=1)
    group:str=Field(max_length=8)
    action:Literal["add","edit","delete"]
    index:int|None=Field(default=None,ge=1,le=30)
    name:str=Field(default="",max_length=120)
    body:str=Field(default="",max_length=50000)
@router.post("/questions/{id}/methods",dependencies=write)
def change_method(id:str,body:MethodChange,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);r=question(db,id,body.revision)
    data=resolve(r.content,r.answer,r.solution,r.question_type,r.question_data)
    if data.warnings:raise HTTPException(422,"题目结构待核对，请先编辑原题")
    groups={str(p.number):p.methods for p in data.subquestions} if data.subquestions else {"main":data.methods}
    if body.group not in groups:raise HTTPException(422,"小问不存在")
    ms=[m for m in groups[body.group] if m.body.strip()];i=(body.index or 0)-1
    before={"solution":r.solution,"question_data":data.model_dump(),"evaluation":bank.read_recommendation(db,r)}
    if body.action=="delete":
        if not 0<=i<len(ms):raise HTTPException(422,"解法不存在")
        ms.pop(i)
    else:
        if not body.body.strip():raise HTTPException(422,"解法正文不能为空")
        if body.action=="edit" and not 0<=i<len(ms):raise HTTPException(422,"解法不存在")
        candidate=Method(name=body.name.strip(),body=body.body,recommended=ms[i].recommended if body.action=="edit" else not ms)
        key=lambda m:bank.matching.strict_text(m.name+"\n"+m.body)
        if any(key(m)==key(candidate) for j,m in enumerate(ms) if body.action!="edit" or j!=i):raise HTTPException(409,"相同解法已存在")
        if body.action=="add":
            if len(ms)>=30:raise HTTPException(422,"每组最多30种解法")
            ms.append(candidate)
        else:ms[i]=candidate
    chosen=next((j for j,m in enumerate(ms) if m.recommended),0)
    ms=[m.model_copy(update={"recommended":j==chosen}) for j,m in enumerate(ms)]
    data=data.model_copy(update={"subquestions":[p.model_copy(update={"methods":ms}) if str(p.number)==body.group else p for p in data.subquestions]}) if data.subquestions else data.model_copy(update={"methods":ms})
    solution=project(data)["solution"]
    if len(solution)>50000:raise HTTPException(422,"解析总长度超过限制")
    validate_images(db,{"solution":solution})
    r.solution=solution;r.question_data=data.model_copy(update={"legacy_digest":digest(r.content,r.answer,solution,r.question_type)}).model_dump()
    r.fingerprint=question_fingerprint(r.content,r.solution,r.answer);r.revision+=1;r.updated_at=now()
    protect_resource_images(db,r);bank.enqueue_recommendation(db,r,user.id)
    record(db,r.id,"method_"+body.action,before,{"solution":solution,"question_data":r.question_data},user.id,r.revision)
    audit(db,"bank.method."+body.action,user.id);db.commit();return recommendation_view(db,r)

@router.get("/questions/{id}/history")
def question_history(id:str,db:Session=Depends(get_db)):
    bank.existing(db,id);return history(db,id)
@router.get("/questions/{id}/video-preview")
def video_preview(id:str,db:Session=Depends(get_db)):
    r=question(db,id)
    facts=r.bank_facts or {}
    if not facts.get("answer_complete") or not facts.get("solution_complete"):return {"ready":False,"solution":"","reason":"请先补齐答案和所有小问解析"}
    try:solution=rec.video_solution(r)
    except ValueError as e:return {"ready":False,"solution":"","reason":str(e)}
    state=bank.read_recommendation(db,r).get("state")
    return {"ready":True,"solution":solution,"reason":"使用当前推荐解法；AI 新评价未确认不会替换" if state in ("queued","running","review") else ""}

class OccurrenceChange(BaseModel):
    revision:int=Field(ge=1)
    source_id:str=Field(max_length=36)
    role:Literal["original","reproduced","adapted"]
    document_id:str=Field(default="",max_length=36)
    item_uid:str=Field(default="",max_length=36)
    original_question_number:str=Field(default="",max_length=40)
    page_start:int|None=Field(default=None,ge=1)
    page_end:int|None=Field(default=None,ge=1)
    chapter:str=Field(default="",max_length=120)
    action:Literal["add","edit","remove"]="edit"
@router.post("/questions/{id}/occurrences",dependencies=write)
def occurrence_change(id:str,body:OccurrenceChange,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);r=question(db,id)
    if r.sources_revision!=body.revision:raise HTTPException(409,"来源版本已变化")
    link=db.get(L,(id,body.source_id,body.role))
    if not link:raise HTTPException(404,"来源关联不存在")
    if body.page_end and (not body.page_start or body.page_end<body.page_start):raise HTTPException(422,"页码范围无效")
    before=bank.link_view(db,r);rows=list(link.occurrences or [])
    idx=next((i for i,o in enumerate(rows) if o.get("document_id")==body.document_id and o.get("item_uid")==body.item_uid),None)
    if body.action=="add":
        if not (body.original_question_number.strip() or body.page_start or body.chapter.strip()):raise HTTPException(422,"请至少填写一个真实出现位置")
        if not rows and (link.original_question_number or link.page_start or link.chapter):
            rows.append({"document_id":"","item_uid":str(uuid4()),"original_question_number":link.original_question_number,"page_start":link.page_start,"page_end":link.page_end,"chapter":link.chapter})
        item={"document_id":"","item_uid":str(uuid4())}
    else:
        if idx is None:raise HTTPException(409,"出现位置已变化")
        item=dict(rows[idx])
    if body.action=="remove":rows.pop(idx)
    else:
        item.update(body.model_dump(include={"original_question_number","page_start","page_end","chapter"}))
        if body.action=="add":
            if any(all(o.get(k)==item.get(k) for k in ("original_question_number","page_start","page_end","chapter")) for o in rows):raise HTTPException(409,"该位置已存在")
            rows.append(item)
        else:
            if any(j!=idx and all(o.get(k)==item.get(k) for k in ("original_question_number","page_start","page_end","chapter")) for j,o in enumerate(rows)):raise HTTPException(409,"该位置已存在")
            rows[idx]=item
    link.occurrences=rows
    first=rows[0] if rows else {}
    for k in ("original_question_number","chapter"):setattr(link,k,first.get(k,""))
    for k in ("page_start","page_end"):setattr(link,k,first.get(k))
    r.sources_revision+=1;r.revision+=1;r.updated_at=now();db.flush()
    record(db,r.id,"occurrence_"+body.action,before,bank.link_view(db,r),user.id,r.revision)
    audit(db,"bank.occurrence",user.id);db.commit();return bank.link_view(db,r)

@router.get("/sources/{id}/questions")
def source_questions(id:str,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),db:Session=Depends(get_db)):
    s=bank.existing(db,id)
    if s.kind!="source":raise HTTPException(422,"请选择来源资料")
    # Expand locations in PostgreSQL; only load the requested page of stems.
    cte="""
    WITH positions AS (
      SELECT r.id,r.code,l.provenance_role AS role,
        o->>'document_id' AS document_id,o->>'item_uid' AS item_uid,
        COALESCE(o->>'original_question_number','') AS original_question_number,
        CASE WHEN o->>'page_start' ~ '^[0-9]{1,9}$' THEN (o->>'page_start')::int END AS page_start,
        CASE WHEN o->>'page_end' ~ '^[0-9]{1,9}$' THEN (o->>'page_end')::int END AS page_end,
        COALESCE(o->>'chapter','') AS chapter
      FROM resource_source_links l JOIN teaching_resources r ON r.id=l.resource_id
      CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_array_length(l.occurrences::jsonb)>0 THEN l.occurrences::jsonb
        ELSE jsonb_build_array(jsonb_build_object('original_question_number',l.original_question_number,'page_start',l.page_start,'page_end',l.page_end,'chapter',l.chapter)) END
      ) o
      WHERE l.source_id=:sid AND r.kind='question' AND NOT r.archived
      UNION ALL
      SELECT r.id,r.code,'original',NULL,NULL,'',NULL,NULL,''
      FROM teaching_resources r WHERE r.source_id=:sid AND r.kind='question' AND NOT r.archived
      AND NOT EXISTS (SELECT 1 FROM resource_source_links l WHERE l.resource_id=r.id AND l.source_id=:sid)
    ), ranked AS (
      SELECT *,row_number() OVER(PARTITION BY id,original_question_number,page_start,page_end,chapter,
        CASE WHEN original_question_number='' AND page_start IS NULL THEN COALESCE(document_id,'')||':'||COALESCE(item_uid,'') ELSE '' END
        ORDER BY document_id NULLS LAST,item_uid NULLS LAST,role) AS rank
      FROM positions
    ), unique_positions AS (SELECT * FROM ranked WHERE rank=1)
    """
    totals=db.execute(text(cte+" SELECT count(*) AS total,count(DISTINCT id) AS questions FROM unique_positions"),{"sid":id}).one()
    number="CASE WHEN p.original_question_number ~ '^[0-9]{1,9}$' THEN p.original_question_number::int END"
    order=number+" NULLS LAST,p.page_start NULLS LAST" if s.source_type=="exam" else "p.page_start NULLS LAST,"+number+" NULLS LAST"
    sql=cte+" SELECT p.id,p.code,r.title,r.content,p.document_id,p.item_uid,p.original_question_number,p.page_start,p.page_end,p.chapter FROM unique_positions p JOIN teaching_resources r ON r.id=p.id ORDER BY "+order+",p.chapter,p.id,p.item_uid NULLS LAST LIMIT :limit OFFSET :offset"
    positions=[dict(x) for x in db.execute(text(sql),{"sid":id,"limit":limit,"offset":offset}).mappings()]
    return {"source":bank.view(s),"total":totals.total,"question_count":totals.questions,"items":positions}

class Selected(BaseModel):
    id:str=Field(max_length=36)
    revision:int=Field(ge=1)
class BulkPlan(BaseModel):
    items:list[Selected]=Field(min_length=1,max_length=2000)
    action:Literal["difficulty","type","knowledge_add","knowledge_remove","source_add","evaluate","archive","restore"]
    value:str=Field(default="",max_length=120)
    confirmed_source:bool=False
def status(db,r,body):
    action=body["action"];v=body["value"]
    if not r or r.kind!="question":return "skip","题目不存在"
    if r.archived!=(action=="restore"):return "skip","归档状态不匹配"
    if action=="difficulty":
        if v not in ("","简单","中等","困难"):return "skip","难度无效"
        if r.difficulty==v:return "unchanged","已设置"
    if action=="type":
        if v not in ("单选题","多选题","填空题","综合题"):return "skip","题型无效"
        if r.question_type==v:return "unchanged","已设置"
        data=resolve(r.content,r.answer,r.solution,r.question_type,r.question_data)
        if data.warnings or (v in ("单选题","多选题"))!=bool(data.options) or (v=="填空题")!=bool(data.blanks) or v=="单选题" and len(data.correct_options)>1:return "skip","题型与结构不兼容"
    if action in ("knowledge_add","knowledge_remove"):
        point=db.get(P,v);link=db.get(K,(r.id,v))
        if action=="knowledge_add":
            if link:return "unchanged","已关联"
            if not point or point.status!="active" or point.subject!=r.subject:return "skip","知识点不可用或科目不同"
            if db.scalar(select(func.count()).select_from(K).where(K.resource_id==r.id))>=20:return "skip","已达20个知识点"
        elif not link:return "unchanged","未关联"
    if action=="source_add":
        src=db.get(R,v)
        if not body["confirmed_source"] or not src or src.kind!="source" or src.archived:return "skip","需要确认真实有效来源"
        if r.source_id==v or any(l.source_id==v for l in bank.links(db,r)):return "unchanged","已关联"
    if action=="evaluate":
        if not (r.bank_facts or {}).get("multi"):return "skip","没有可比较的多解法"
        if bank.read_recommendation(db,r).get("state") in ("queued","running"):return "unchanged","已在评价队列"
    if action=="restore":
        if db.scalar(select(R.id).where(R.kind=="question",R.archived==False,R.stem_key==r.stem_key,R.id!=r.id).limit(1)):return "skip","有效题库存在相同题干"
    return "ready",""
def bulk_view(data):
    return {k:v for k,v in data.items() if k!="body"}
@router.post("/bulk/preview",dependencies=write)
def preview_bulk(body:BulkPlan,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);payload=body.model_dump()
    if len({x.id for x in body.items})!=len(body.items):raise HTTPException(422,"题目重复")
    rows=[]
    for item in body.items:
        r=db.get(R,item.id)
        state,reason=status(db,r,payload)
        if r and r.revision!=item.revision:state,reason="skip","题目版本已变化"
        rows.append({"id":item.id,"revision":item.revision,"code":r.code if r else item.id,"state":state,"reason":reason})
    ident=str(uuid4());plan={"id":ident,"state":"preview","rows":rows,"body":payload,"next":0,"created_at":now(),"owner":user.id}
    store(db,"bank.bulk."+ident,plan);db.commit();return bulk_view(plan)
def bulk_get(db,id,user):
    plan=read_setting(db,"bank.bulk."+id)
    if not plan or plan["owner"]!=user.id:raise HTTPException(404,"批量任务不存在")
    return plan
@router.get("/bulk/{id}")
def get_bulk(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return bulk_view(bulk_get(db,id,user))
@router.get("/bulk")
def bulk_history(db:Session=Depends(get_db),user:User=Depends(current_user)):
    rows=[json.loads(s.value) for s in db.scalars(select(Setting).where(Setting.key.startswith("bank.bulk.")))]
    return [bulk_view(p) for p in sorted(rows,key=lambda p:p["created_at"],reverse=True)[:20] if p["owner"]==user.id]
class BulkStep(BaseModel):
    offset:int=Field(ge=0)
@router.post("/bulk/{id}/step",dependencies=write)
def bulk_step(id:str,body:BulkStep,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);plan=bulk_get(db,id,user);payload=plan["body"]
    if body.offset<plan["next"] or plan["state"]=="completed":return bulk_view(plan)
    if body.offset!=plan["next"] or plan["state"]=="cancelled":raise HTTPException(409,"批次顺序已变化")
    batch=plan["rows"][body.offset:body.offset+20]
    for item in batch:
        if item["state"] not in ("ready","failed"):continue
        try:
            with db.begin_nested():
                r=bank.existing(db,item["id"],True)
                if r.revision!=item["revision"]:raise HTTPException(409,"题目版本已变化")
                state,reason=status(db,r,payload)
                if state!="ready":item.update(state=state,reason=reason);continue
                act=payload["action"];v=payload["value"]
                before=bank.view(r);old_rec=bank.read_recommendation(db,r)
                if act=="difficulty":r.difficulty=v
                elif act=="type":
                    r.question_type=v
                    data=resolve(r.content,r.answer,r.solution,before["question_type"],r.question_data)
                    r.question_data=data.model_copy(update={"legacy_digest":digest(r.content,r.answer,r.solution,v)}).model_dump()
                elif act=="knowledge_add":db.add(K(resource_id=r.id,knowledge_id=v,role="related"))
                elif act=="knowledge_remove":db.delete(db.get(K,(r.id,v)))
                elif act=="source_add":docs.attach_review_source(db,r,v)
                elif act in ("archive","restore"):r.archived=act=="archive"
                elif act=="evaluate":
                    bank.enqueue_recommendation(db,r,user.id)
                if act!="evaluate":
                    r.revision+=1;r.updated_at=now()
                    if act in ("knowledge_add","knowledge_remove"):
                        db.flush();r.tags=[x.name for x in db.execute(select(P.name).join(K,K.knowledge_id==P.id).where(K.resource_id==r.id))]
                    # Metadata-only changes do not invalidate a confirmed recommendation.
                    if old_rec and act not in ("archive","restore","type"):bank.store_recommendation(db,r,{**old_rec,"revision":r.revision})
                db.flush()
                record(db,r.id,"bulk_"+act,before,bank.view(r),user.id,r.revision)
                item.update(state="done",reason="")
        except (HTTPException,SQLAlchemyError) as e:item.update(state="failed",reason=str(e.detail)[:300] if isinstance(e,HTTPException) else "数据库写入失败")
    plan["next"]+=len(batch);plan["state"]="completed" if plan["next"]>=len(plan["rows"]) else "running"
    store(db,"bank.bulk."+id,plan);audit(db,"bank.bulk.step",user.id);db.commit();return bulk_view(plan)
@router.post("/bulk/{id}/retry",dependencies=write)
def bulk_retry(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);previous=bulk_get(db,id,user)
    if previous["state"] not in ("completed","cancelled"):raise HTTPException(409,"请先完成或取消旧任务")
    payload=dict(previous["body"]);payload["items"]=[{"id":r["id"],"revision":r["revision"]} for r in previous["rows"] if r["state"]=="failed"]
    if not payload["items"]:raise HTTPException(422,"没有失败条目")
    # Stale versions remain blocked; never rebase a previous confirmation automatically.
    return preview_bulk(BulkPlan.model_validate(payload),db,user)

@router.post("/bulk/{id}/cancel",dependencies=write)
def bulk_cancel(id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);p=bulk_get(db,id,user)
    if p["state"]!="completed":p["state"]="cancelled";store(db,"bank.bulk."+id,p);db.commit()
    return bulk_view(p)

class CartChange(BaseModel):
    revision:int=Field(ge=0)
    ids:list[str]=Field(max_length=200)
def cart_key(user):return "bank.cart."+str(user.id)
def cart(db,user):
    return read_setting(db,cart_key(user),{"revision":0,"ids":[]})
def cart_view(db,user):
    state=cart(db,user);rows={r.id:r for r in db.scalars(select(R).where(R.id.in_(state["ids"])))}
    return {**state,"items":[bank.view(rows[i]) for i in state["ids"] if i in rows]}
@router.get("/cart")
def get_cart(db:Session=Depends(get_db),user:User=Depends(current_user)):return cart_view(db,user)
@router.put("/cart",dependencies=write)
def update_cart(body:CartChange,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);old=cart(db,user)
    if old["revision"]!=body.revision:raise HTTPException(409,"选题清单已变化，请刷新")
    ids=list(dict.fromkeys(body.ids))
    for ident in ids:
        if ident not in old["ids"]:question(db,ident)
    store(db,cart_key(user),{"revision":old["revision"]+1,"ids":ids});db.commit();return cart_view(db,user)
class CartConfirm(BaseModel):
    revision:int=Field(ge=0)
    kind:Literal["paper","handout","textbook"]
    title:str=Field(min_length=1,max_length=200)
    items:list[Selected]=Field(min_length=1,max_length=200)
    request_id:str=Field(min_length=1,max_length=36)
@router.post("/cart/confirm",dependencies=write)
def confirm_cart(body:CartConfirm,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);receipt="bank.cart.receipt."+str(user.id)+"."+body.request_id
    old=read_setting(db,receipt)
    if old:
        if old["input"]!=body.model_dump():raise HTTPException(409,"请求编号已使用")
        return {"document_id":old["document_id"]}
    state=cart(db,user)
    if state["revision"]!=body.revision or state["ids"]!=[i.id for i in body.items]:raise HTTPException(409,"清单已变化，请刷新")
    for i in body.items:question(db,i.id,i.revision)
    draft=docs.Draft(kind=body.kind,title=body.title,blocks=[docs.Block(uid=str(uuid4()),kind="reference",resource_id=i.id) for i in body.items])
    d=TeachingDocument(id=str(uuid4()),title=body.title.strip(),kind=body.kind,subject="",source_id=None,blocks=docs.validate(db,draft,[]),revision=1,archived=False,created_at=now(),updated_at=now())
    db.add(d);db.flush();docs.references(db,d)
    store(db,receipt,{"input":body.model_dump(),"document_id":d.id})
    audit(db,"bank.cart.confirm",user.id);db.commit();return {"document_id":d.id}

class ExportSelection(BaseModel):
    items:list[Selected]=Field(min_length=1,max_length=200)
    request_id:str=Field(min_length=1,max_length=36)
@router.post("/export",dependencies=write)
def export_selection(body:ExportSelection,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bank.admin_lock(db,user);key="bank.export."+str(user.id)+"."+body.request_id
    old=read_setting(db,key)
    if old:
        if old["input"]!=body.model_dump():raise HTTPException(409,"请求编号已使用")
        return {"document_id":old["document_id"]}
    if len({i.id for i in body.items})!=len(body.items):raise HTTPException(422,"选题重复")
    for i in body.items:question(db,i.id,i.revision)
    draft=docs.Draft(kind="paper",title="题库选题导出",blocks=[docs.Block(uid=str(uuid4()),kind="reference",resource_id=i.id) for i in body.items])
    d=TeachingDocument(id=str(uuid4()),title=draft.title,kind=draft.kind,subject="",source_id=None,blocks=docs.validate(db,draft,[]),revision=1,archived=False,created_at=now(),updated_at=now())
    db.add(d);db.flush();docs.references(db,d)
    store(db,key,{"input":body.model_dump(),"document_id":d.id});audit(db,"bank.export",user.id);db.commit()
    return {"document_id":d.id}
