"""Knowledge catalog and graph, distinct from teaching units."""
import unicodedata
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, or_, func
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user, require_origin, audit, now
from app.core.solution_methods import normalize_subject
from app.models import KnowledgePointCatalog as Point, KnowledgeAlias as Alias, KnowledgeRelation as Edge, ResourceKnowledgeLink as Link, TeachingResource as Resource, User
from app.api.resources import admin_lock, existing, view

router=APIRouter(prefix="/knowledge",tags=["knowledge"],dependencies=[Depends(current_user)])
def norm(s): return unicodedata.normalize("NFKC",s).strip().casefold()
def point(db,id):
    p=db.get(Point,id)
    if not p: raise HTTPException(404,"知识点不存在")
    return p
def public(db,p):
    return {**{k:getattr(p,k) for k in ("id","code","name","subject","chapter","description","status","replaced_by_id","revision","created_at","updated_at")},"aliases":list(db.scalars(select(Alias.alias).where(Alias.knowledge_id==p.id).order_by(Alias.normalized)))}
def edge_view(e): return {k:getattr(e,k) for k in ("source_id","target_id","relation_type")}
def would_cycle(edges,source,target,kind):
    adjacency={}
    for a,b,t in edges:
        if t==kind: adjacency.setdefault(a,[]).append(b)
    todo=[target];seen=set()
    while todo:
        x=todo.pop()
        if x==source:return True
        if x not in seen:
            seen.add(x);todo.extend(adjacency.get(x,[]))
    return False
class Draft(BaseModel):
    name:str=Field(min_length=1,max_length=180)
    subject:str=Field(min_length=1,max_length=40)
    chapter:str=Field(default="",max_length=120)
    description:str=Field(default="",max_length=16000)
    aliases:list[str]=Field(default_factory=list,max_length=30)
    status:Literal["active","disabled"]="active"
    revision:int|None=Field(default=None,ge=1)
class Relation(BaseModel):
    source_id:str=Field(max_length=36)
    target_id:str=Field(max_length=36)
    relation_type:Literal["contains","prerequisite","related"]
class ResourceLink(BaseModel):
    knowledge_id:str=Field(max_length=36)
    role:Literal["core","related"]="related"
class ResourceLinks(BaseModel):
    revision:int=Field(ge=1)
    items:list[ResourceLink]=Field(max_length=100)
@router.get("/points")
def list_points(q:str=Query("",max_length=180),subject:str="",include_disabled:bool=False,limit:int=Query(200,ge=1,le=500),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    stmt=select(Point)
    if not include_disabled: stmt=stmt.where(Point.status=="active")
    if subject: stmt=stmt.where(Point.subject==normalize_subject(subject))
    if q.strip():
        term=q.strip()
        stmt=stmt.where(or_(Point.name.contains(term,autoescape=True),Point.code.contains(term.upper(),autoescape=True),Point.id.in_(select(Alias.knowledge_id).where(Alias.normalized.contains(norm(term),autoescape=True)))))
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {"items":[public(db,p) for p in db.scalars(stmt.order_by(Point.subject,Point.chapter,Point.name,Point.id).offset(offset).limit(limit))],"total":total}
@router.get("/browse")
def browse(subject:str=Query(...,min_length=1,max_length=40),chapter:str|None=Query(None,max_length=120),
           parent_id:str|None=Query(None,max_length=36),q:str=Query("",max_length=180),
           limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    """Lazy, subject-scoped hierarchy. Only explicit contains edges form folders."""
    subject=normalize_subject(subject)
    active=select(Point.id).where(Point.subject==subject,Point.status=="active")
    child_ids=select(Edge.target_id).where(Edge.relation_type=="contains",Edge.source_id.in_(active))
    roots=select(Point).where(Point.subject==subject,Point.status=="active",Point.id.not_in(child_ids))
    stmt=select(Point).where(Point.subject==subject,Point.status=="active")
    term=q.strip()
    if term:
        stmt=stmt.where(or_(Point.name.contains(term,autoescape=True),Point.code.contains(term.upper(),autoescape=True),
            Point.id.in_(select(Alias.knowledge_id).where(Alias.normalized.contains(norm(term),autoescape=True)))))
    elif parent_id:
        parent=point(db,parent_id)
        if parent.subject!=subject or parent.status!="active":raise HTTPException(422,"上级知识点不属于当前有效学科")
        stmt=stmt.where(Point.id.in_(select(Edge.target_id).where(Edge.source_id==parent_id,Edge.relation_type=="contains")))
    elif chapter is not None:
        stmt=roots.where(Point.chapter==chapter)
    else:
        grouped=roots.with_only_columns(Point.chapter.label("chapter"),func.count().label("count")).group_by(Point.chapter).subquery()
        total=db.scalar(select(func.count()).select_from(grouped))
        rows=db.execute(select(grouped).order_by(grouped.c.chapter).offset(offset).limit(limit)).all()
        return {"mode":"chapters","items":[{"chapter":r.chapter,"count":r.count} for r in rows],"total":total}
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=list(db.scalars(stmt.order_by(Point.name,Point.id).offset(offset).limit(limit)))
    counts=dict(db.execute(select(Edge.source_id,func.count()).where(Edge.relation_type=="contains",
        Edge.source_id.in_([p.id for p in rows]),Edge.target_id.in_(active)).group_by(Edge.source_id)).all()) if rows else {}
    return {"mode":"points","items":[{"id":p.id,"name":p.name,"chapter":p.chapter,"child_count":counts.get(p.id,0)} for p in rows],"total":total}

def save(db,p,body):
    name=body.name.strip();subject=normalize_subject(body.subject);key=norm(name)
    if not name or not subject or len(key)>200:raise HTTPException(422,"知识点名称和学科不能为空")
    if db.scalar(select(Point.id).where(Point.subject==subject,Point.name_key==key,Point.id!=p.id)):raise HTTPException(409,"该学科下已存在同名知识点")
    aliases={}
    for a in body.aliases:
        if len(a)>180 or len(norm(a))>180:raise HTTPException(422,"别名过长")
        if norm(a) and norm(a)!=key: aliases[norm(a)]=a.strip()
    p.name=name;p.name_key=key;p.subject=subject;p.chapter=body.chapter.strip();p.description=body.description;p.status=body.status;p.updated_at=now()
    db.flush()
    db.execute(delete(Alias).where(Alias.knowledge_id==p.id))
    for key,a in aliases.items():db.add(Alias(knowledge_id=p.id,normalized=key,alias=a))
@router.post("/points",dependencies=[Depends(require_origin)])
def create(body:Draft,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user)
    while True:
        code="KP"+uuid4().hex[:8].upper()
        if not db.scalar(select(Point.id).where(Point.code==code)):break
    p=Point(id=str(uuid4()),code=code,revision=1,created_at=now(),replaced_by_id=None)
    db.add(p)
    # Populate mandatory fields before any autoflush.
    with db.no_autoflush: save(db,p,body)
    audit(db,"knowledge.create",user.id);db.commit();return public(db,p)
@router.put("/points/{id}",dependencies=[Depends(require_origin)])
def update(id:str,body:Draft,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);p=point(db,id)
    if p.revision!=body.revision or p.status=="replaced":raise HTTPException(409,"知识点版本冲突或已替换")
    save(db,p,body);p.revision+=1;audit(db,"knowledge.update",user.id);db.commit();return public(db,p)
@router.get("/relations")
def relations(db:Session=Depends(get_db)):
    rows=list(db.scalars(select(Edge).order_by(Edge.source_id,Edge.target_id,Edge.relation_type).limit(5001)))
    return {"items":[edge_view(e) for e in rows[:5000]],"truncated":len(rows)>5000}
@router.post("/relations",dependencies=[Depends(require_origin)])
def add_relation(body:Relation,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);a,b,t=body.source_id,body.target_id,body.relation_type
    if a==b or point(db,a).status!="active" or point(db,b).status!="active":raise HTTPException(422,"关系两端须为不同的有效知识点")
    if t=="related":a,b=sorted((a,b))
    old=db.get(Edge,(a,b,t))
    if old:return edge_view(old)
    rows=db.execute(select(Edge.source_id,Edge.target_id,Edge.relation_type)).all()
    if t!="related" and would_cycle(rows,a,b,t):raise HTTPException(409,"该关系会形成循环")
    # A contains edge is the hierarchy parent; one parent per child.
    if t=="contains" and any(y==b and k=="contains" for _,y,k in rows):raise HTTPException(409,"此知识点已有上级，请先解除")
    e=Edge(source_id=a,target_id=b,relation_type=t);db.add(e);audit(db,"knowledge.relation.create",user.id);db.commit();return edge_view(e)
@router.delete("/relations",dependencies=[Depends(require_origin)])
def remove_relation(source_id:str,target_id:str,relation_type:Literal["contains","prerequisite","related"],db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user)
    if relation_type=="related":source_id,target_id=sorted((source_id,target_id))
    e=db.get(Edge,(source_id,target_id,relation_type))
    if e:db.delete(e);audit(db,"knowledge.relation.remove",user.id);db.commit()
    return {"ok":True}
@router.get("/points/{id}/resources")
def point_resources(id:str,db:Session=Depends(get_db)):
    point(db,id)
    stmt=select(Resource).join(Link,Link.resource_id==Resource.id).where(Link.knowledge_id==id,Resource.archived==False).order_by(Resource.updated_at.desc()).limit(100)
    return [view(r) for r in db.scalars(stmt)]
def resource_links(db,r):
    return {"revision":r.revision,"items":[{"knowledge_id":l.knowledge_id,"role":l.role,"name":point(db,l.knowledge_id).name,"code":point(db,l.knowledge_id).code} for l in db.scalars(select(Link).where(Link.resource_id==r.id))]}
@router.get("/resources/{id}")
def get_links(id:str,db:Session=Depends(get_db)):return resource_links(db,existing(db,id))
@router.put("/resources/{id}",dependencies=[Depends(require_origin)])
def set_links(id:str,body:ResourceLinks,db:Session=Depends(get_db),user:User=Depends(current_user)):
    admin_lock(db,user);r=existing(db,id,True)
    if r.archived or r.kind=="source" or r.revision!=body.revision:raise HTTPException(409,"资源不可编辑或版本冲突")
    if len({i.knowledge_id for i in body.items})!=len(body.items) or sum(i.role=="core" for i in body.items)>1:raise HTTPException(422,"知识点不能重复，核心知识点最多一个")
    previous={l.knowledge_id for l in db.scalars(select(Link).where(Link.resource_id==id))}
    for i in body.items:
        if point(db,i.knowledge_id).status!="active" and i.knowledge_id not in previous:raise HTTPException(422,"知识点已停用")
    db.execute(delete(Link).where(Link.resource_id==id))
    for i in body.items:db.add(Link(resource_id=id,**i.model_dump()))
    r.tags=[point(db,i.knowledge_id).name for i in body.items][:20]
    r.revision+=1;r.updated_at=now();audit(db,"resource.knowledge.update",user.id);db.commit();return resource_links(db,r)
