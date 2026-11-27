"""Authenticated finished works catalogue. Videos remain in the existing engine."""
from typing import Literal
from uuid import uuid4
from pathlib import Path
import os, shutil, tempfile, zipfile, threading, time, re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from sqlalchemy import select, func, literal, cast, Integer, or_, delete
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import current_user, require_origin, audit, now
from app.models import (User, TeachingWork, TeachingWorkVersion, TeachingWorkAsset,
                        TeachingWorkPendingCover, StoredFile, StudioItem, VideoProject, TeachingDocument, TeachingResource, FileReference)
from app.services import storage, teaching_works
from app.services.finished_pdf_preview import render_page

router = APIRouter(prefix="/teaching-works", tags=["teaching-works"], dependencies=[Depends(current_user)])
FIELDS = ("id", "title", "kind", "subject", "origin_scope", "origin_id",
          "current_version", "created_at", "updated_at")


def summary(work):
    return {key: getattr(work, key) for key in FIELDS}


def owned(db, user, ident):
    work = db.scalar(select(TeachingWork).where(TeachingWork.id == ident, TeachingWork.user_id == user.id))
    if work is None:
        raise HTTPException(404, "作品不存在")
    return work


def video_records(user):
    # Existing video records are private to the installation's single administrator.
    return select(
        StudioItem.id.label("id"), StudioItem.title.label("title"), literal("video").label("kind"),
        func.coalesce(VideoProject.source_snapshot["subject"].as_string(), "").label("subject"),
        literal("video").label("origin_scope"), VideoProject.id.label("origin_id"),
        cast(literal(None), Integer).label("current_version"),
        StudioItem.created_at.label("created_at"), StudioItem.updated_at.label("updated_at"),
    ).join(VideoProject, VideoProject.work_id == StudioItem.id).where(
        StudioItem.kind == "work", StudioItem.archived == False,
        StudioItem.data["category"].as_string() == "video",
        VideoProject.engine_id.is_not(None), literal(user.id == 1))


def split_terms(value):
    return list(dict.fromkeys(t.strip() for t in value.replace("，",",").split(",") if t.strip()))


def has_fact(db, column, field, value):
    if db.bind.dialect.name == "postgresql":
        return cast(column,JSONB).contains({field:[value]})
    values = func.json_each(column, "$."+field).table_valued("key","value").alias()
    return select(literal(1)).select_from(values).where(values.c.value==value).exists()


@router.get("")
def listing(q: str = Query("", max_length=200), kind: str = Query("", max_length=20),
            subject: str = Query("", max_length=40),
            scope: Literal["", "doc", "source", "video"] = "",
            sort: Literal["recent", "old", "name"] = "recent",
            created_from: int | None = Query(None, ge=0),
            created_to: int | None = Query(None, ge=0),
            offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), user: User = Depends(current_user),
            source_type: str = "", institution: str = "", year: str = "",
            knowledge_point: str = "", knowledge_tag: str = "", subjects_all: str = ""):
    filters = {"source_types":source_type,"institutions":institution,"years":year,
               "knowledge_points":knowledge_point,"knowledge_tags":knowledge_tag,"subjects":subjects_all}
    if any(len(value)>500 for value in filters.values()):
        raise HTTPException(422,"筛选内容过长")
    terms = {field:split_terms(value) for field,value in filters.items() if value.strip()}
    docs = select(*(getattr(TeachingWork, key).label(key) for key in FIELDS)).where(
        TeachingWork.user_id == user.id)
    videos = video_records(user)
    if terms:
        docs = docs.join(TeachingWorkVersion, (TeachingWorkVersion.work_id == TeachingWork.id) &
                         (TeachingWorkVersion.number == TeachingWork.current_version))
        for field,values in terms.items():
            for value in values:
                if field == "subjects":
                    docs = docs.where(or_(TeachingWork.subject==value,has_fact(db,TeachingWorkVersion.facets,field,value)))
                    videos = videos.where(or_(VideoProject.source_snapshot["subject"].as_string()==value,
                                              has_fact(db,VideoProject.work_facets,field,value)))
                else:
                    docs = docs.where(has_fact(db,TeachingWorkVersion.facets,field,value))
                    videos = videos.where(has_fact(db,VideoProject.work_facets,field,value))
    combined = docs.union_all(videos).subquery()
    stmt = select(combined)
    if q.strip():
        stmt = stmt.where(combined.c.title.contains(q.strip(), autoescape=True))
    if kind:
        stmt = stmt.where(combined.c.kind == kind)
    if subject:
        stmt = stmt.where(combined.c.subject == subject)
    if scope:
        stmt = stmt.where(combined.c.origin_scope == scope)
    if created_from is not None:
        stmt = stmt.where(combined.c.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(combined.c.created_at < created_to)
    if created_from is not None and created_to is not None and created_from >= created_to:
        raise HTTPException(422, "创建时间范围无效")
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {"recent": combined.c.updated_at.desc(), "old": combined.c.created_at.asc(),
             "name": combined.c.title.asc()}[sort]
    rows = [dict(r) for r in db.execute(stmt.order_by(order, combined.c.id).offset(offset).limit(limit)).mappings()]
    return {"items": rows, "total": total}


@router.get("/subjects")
def subjects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    docs = select(*(getattr(TeachingWork, key).label(key) for key in FIELDS)).where(
        TeachingWork.user_id == user.id)
    rows = docs.union_all(video_records(user)).subquery()
    return list(db.scalars(select(rows.c.subject).where(rows.c.subject != "").distinct().order_by(rows.c.subject)))


@router.get("/{ident}")
def detail(ident: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    work = db.scalar(select(TeachingWork).where(TeachingWork.id == ident, TeachingWork.user_id == user.id))
    if work is None:
        video = video_records(user).subquery()
        found = db.execute(select(video).where(video.c.id == ident)).mappings().first()
        if not found:
            raise HTTPException(404, "作品不存在")
        item = db.get(StudioItem, ident)
        project = db.get(VideoProject, found["origin_id"])
        cover = item.data.get("cover_file_id")
        return {**dict(found), "versions": [], "pending_cover": None, "facets": project.work_facets,
                "video": {"project_id": project.id, "resource_id": project.resource_id,
                          "cover_file_id": cover, "revision_managed_by_engine": True}}
    # Do not load complete document snapshots in the file/detail request.
    versions = db.execute(select(TeachingWorkVersion.number, TeachingWorkVersion.created_at, TeachingWorkVersion.facets).where(
        TeachingWorkVersion.work_id == work.id).order_by(TeachingWorkVersion.number.desc())).all()
    assets = list(db.execute(select(TeachingWorkAsset, StoredFile).join(
        StoredFile, StoredFile.id == TeachingWorkAsset.file_id).where(TeachingWorkAsset.work_id == work.id)))
    pending = db.execute(select(TeachingWorkPendingCover.filename, TeachingWorkPendingCover.created_at).where(
        TeachingWorkPendingCover.work_id == work.id)).first()
    return {**summary(work), "facets": next((v.facets for v in versions if v.number==work.current_version),{}), "pending_cover": {"filename":pending.filename,"created_at":pending.created_at} if pending else None,
            "versions": [{"number": v.number, "created_at": v.created_at, "files": [
                {"role": a.role, "filename": a.filename, "pages": a.pages,
                 "size_bytes": f.size_bytes, "media_type": f.media_type}
                for a, f in assets if a.version == v.number]} for v in versions]}


def snapshot_questions(snapshot):
    """Recorded knowledge names and graph tags are distinct. Never read the live bank for a historical work."""
    result = []
    chapter = ""
    for b in snapshot.get("doc", {}).get("blocks", []):
        if b.get("kind") == "heading":
            chapter = b.get("title") or chapter
        ref = b.get("snapshot") or {}
        if b.get("kind") != "question" and not (b.get("kind") == "reference" and ref.get("kind") == "question"):
            continue
        item = {**ref}
        if b.get("kind") == "question":
            item.update(b)
        else:
            for field in b.get("local_fields", []):
                item[field] = b.get(field, "")
        for field in b.get("hidden_fields", []):
            item[field] = ""
        recorded = item.get("tags", []) if b.get("kind") == "reference" else b.get("knowledge_tags", [])
        labels = ref.get("knowledge_tags", []) if b.get("kind") == "reference" else []
        result.append({
            "uid": b.get("uid"), "resource_id": b.get("resource_id"), "chapter": chapter or item.get("chapter", ""),
            "title": item.get("title", ""), "content": item.get("content", ""), "answer": item.get("answer", ""),
            "solution": item.get("solution", ""), "analysis": item.get("analysis", ""), "proof": item.get("proof", ""),
            "knowledge_points": [x for x in recorded if isinstance(x, str)],
            "knowledge_tags": [x["name"] for x in labels if isinstance(x, dict) and isinstance(x.get("name"), str)],
            "source_id": item.get("source_id"), "subject": item.get("subject", ""),
        })
    return result


@router.get("/{ident}/versions/{number}/questions")
def questions(ident: str, number: int, q: str = Query("", max_length=200),
              offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    work = owned(db, user, ident)
    version = db.get(TeachingWorkVersion, (work.id, number))
    if not version:
        raise HTTPException(404, "作品版本不存在")
    items = snapshot_questions(version.snapshot)
    points = sorted({p for item in items for p in item["knowledge_points"]})
    tags = sorted({p for item in items for p in item["knowledge_tags"]})
    sources = {item["source_id"] for item in items if item["source_id"]}
    count = len(items)
    if q.strip():
        needle = q.strip().casefold()
        items = [item for item in items if needle in (str(item["title"])+" "+str(item["content"])).casefold()]
    return {"items": items[offset:offset+limit], "total": len(items), "question_count": count,
            "knowledge_points": points, "knowledge_tags": tags, "source_count": len(sources),
            "partial_pages": bool(version.snapshot.get("edition", {}).get("page_ranges")), "sources":version.facets.get("sources",[])}


@router.get("/{ident}/pending-cover/file")
def pending_cover_file(ident: str, download: bool = False, db: Session = Depends(get_db),
                       user: User = Depends(current_user)):
    work = owned(db, user, ident)
    asset = db.get(TeachingWorkPendingCover, work.id)
    if not asset:
        raise HTTPException(404, "待配对书衣不存在")
    item = db.get(StoredFile, asset.file_id)
    return file_response(item, asset.filename, download)


def file_response(item, filename, download):
    return FileResponse(storage.file_path(item), media_type=item.media_type, filename=filename,
                        content_disposition_type="attachment" if download else "inline",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.get("/{ident}/versions/{number}/files/{role}")
def read_file(ident: str, number: int, role: str, download: bool = False,
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    work = owned(db, user, ident)
    asset = db.get(TeachingWorkAsset, (work.id, number, role))
    if asset is None:
        raise HTTPException(404, "成品文件不存在")
    item = db.get(StoredFile, asset.file_id)
    return file_response(item, asset.filename, download)


class RestoreRequest(BaseModel):
    expected_version: int = Field(ge=1)


@router.post("/{ident}/versions/{number}/restore", dependencies=[Depends(require_origin)])
def restore(ident: str, number: int, body: RestoreRequest, db: Session = Depends(get_db),
            user: User = Depends(current_user)):
    wid, version = teaching_works.restore_version(db, user_id=user.id, work_id=ident,
                                                   number=number, expected=body.expected_version)
    db.commit()
    return {"id":wid, "current_version":version}


@router.get("/{ident}/edit-context")
def edit_context(ident: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    work = owned(db, user, ident)
    origin = db.get(TeachingDocument if work.origin_scope == "doc" else TeachingResource, work.origin_id)
    if not origin or origin.archived:
        raise HTTPException(409, "原制作项目已不存在或已归档，成品仍可使用")
    version = db.get(TeachingWorkVersion, (work.id, work.current_version))
    if not version:
        raise HTTPException(409, "尚无正式正文版本")
    snap = version.snapshot
    return {"origin_scope":work.origin_scope,"origin_id":work.origin_id,
            "kind":snap.get("doc",{}).get("kind"),"version":version.number,
            "layout":snap.get("layout",{}),"edition":snap.get("edition",{}),
            "export_token":snap.get("doc",{}).get("export_token"),
            "overrides":snap.get("overrides",{}),"wrap":snap.get("wrap")}


@router.get("/{ident}/versions/{number}/files/{role}/pages/{page}")
def preview_page(ident: str, number: int, role: str, page: int, dpi: int = Query(120, ge=72, le=180),
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    work = owned(db, user, ident)
    asset = db.get(TeachingWorkAsset, (work.id, number, role))
    if not asset or not 1 <= page <= asset.pages:
        raise HTTPException(404, "成品或页码不存在")
    item = db.get(StoredFile, asset.file_id)
    path = storage.file_path(item)
    db.rollback()
    return Response(render_page(path, page, dpi), media_type="image/png",
                    headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


@router.get("/{ident}/pending-cover/pages/{page}")
def preview_pending(ident: str, page: int, dpi: int = Query(120, ge=72, le=180),
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    work = owned(db, user, ident)
    pending = db.get(TeachingWorkPendingCover, work.id)
    if not pending or page != 1:
        raise HTTPException(404, "待配对书衣不存在")
    path = storage.file_path(db.get(StoredFile, pending.file_id))
    db.rollback()
    return Response(render_page(path, page, dpi), media_type="image/png",
                    headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


zip_slots=threading.BoundedSemaphore(1)

def lock_admin(db,user):
    db.scalar(select(User.id).where(User.id==user.id).with_for_update())

class WorkChoice(BaseModel):
    id:str=Field(min_length=1,max_length=36)
    version:int|None=Field(default=None,ge=0)
class Choices(BaseModel):
    items:list[WorkChoice]=Field(min_length=1,max_length=100)
class RenameRequest(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    expected_updated:int

def resolve_choice(db,user,choice):
    work=db.scalar(select(TeachingWork).where(TeachingWork.id==choice.id,TeachingWork.user_id==user.id).with_for_update())
    if work:
        if work.current_version!=choice.version:raise HTTPException(409,"作品版本已变化，请刷新")
        return work,None
    video=video_records(user).subquery()
    found=db.execute(select(video).where(video.c.id==choice.id)).mappings().first()
    if not found or choice.version is not None:raise HTTPException(404,"作品不存在")
    return None,found

def current_assets(db,work):
    rows=list(db.scalars(select(TeachingWorkAsset).where(TeachingWorkAsset.work_id==work.id,TeachingWorkAsset.version==work.current_version)))
    if not any(a.role=="body" for a in rows):raise HTTPException(409,"尚无正式正文")
    return rows

@router.patch("/{ident}/name",dependencies=[Depends(require_origin)])
def rename(ident:str,body:RenameRequest,db:Session=Depends(get_db),user:User=Depends(current_user)):
    lock_admin(db,user)
    title=body.title.strip()
    if not title:raise HTTPException(422,"名称不能为空")
    work=db.scalar(select(TeachingWork).where(TeachingWork.id==ident,TeachingWork.user_id==user.id).with_for_update())
    if work:
        if work.updated_at!=body.expected_updated:raise HTTPException(409,"作品已更新")
        work.title=title;work.updated_at=now()
    else:
        _,video=resolve_choice(db,user,WorkChoice(id=ident))
        row=db.get(StudioItem,video["id"])
        if row.updated_at!=body.expected_updated:raise HTTPException(409,"作品已更新")
        from app.api.studio import save_version
        row.title=title;row.revision+=1;row.updated_at=now();save_version(db,row)
    audit(db,"teaching_work.rename",user.id);db.commit()
    return {"title":title}

@router.post("/manage/delete",dependencies=[Depends(require_origin)])
def delete_works(body:Choices,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from app.api import document_pdf
    with document_pdf.lock:
        lock_admin(db,user)
        targets=[]
        for choice in {c.id:c for c in body.items}.values():
            work,video=resolve_choice(db,user,choice)
            if work and any(j.user_id==user.id and j.scope==work.origin_scope and j.identity==work.origin_id and j.state not in document_pdf.TERMINAL for j in document_pdf.jobs.values()):
                raise HTTPException(409,"作品正在导出")
            if video and db.scalar(select(StudioItem.id).where(StudioItem.kind=="publication",StudioItem.archived==False,StudioItem.data["work_id"].as_string()==choice.id).limit(1)):
                raise HTTPException(409,"视频仍有发布记录")
            targets.append((work,video))
        for work,video in targets:
            if work:
                for number in db.scalars(select(TeachingWorkVersion.number).where(TeachingWorkVersion.work_id==work.id)):
                    db.execute(delete(FileReference).where(FileReference.owner_type==teaching_works.OWNER,FileReference.owner_id==teaching_works.version_owner(work.id,number)))
                teaching_works.remove_pending(db,db.get(TeachingWorkPendingCover,work.id))
                db.execute(delete(TeachingWorkAsset).where(TeachingWorkAsset.work_id==work.id))
                db.execute(delete(TeachingWorkVersion).where(TeachingWorkVersion.work_id==work.id))
                db.delete(work)
            else:
                from app.api.studio import save_version
                row=db.get(StudioItem,video["id"]);row.archived=True;row.revision+=1;row.updated_at=now();save_version(db,row)
        audit(db,"teaching_work.delete",user.id);db.commit()
    return {"removed":len(targets),"videos_archived":sum(v is not None for _,v in targets)}

@router.post("/manage/zip",dependencies=[Depends(require_origin)])
def download_zip(body:Choices,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not zip_slots.acquire(blocking=False):raise HTTPException(429,"已有打包任务")
    folder=None
    try:
        folder=Path(tempfile.mkdtemp(prefix="work-zip-",dir=storage.root()))
        lock_admin(db,user)
        staged=[];total=0
        for choice in {c.id:c for c in body.items}.values():
            work,video=resolve_choice(db,user,choice)
            if video:raise HTTPException(422,"视频请单独下载")
            for a in current_assets(db,work):
                item=db.get(StoredFile,a.file_id);total+=item.size_bytes
                if total>500*1024*1024:raise HTTPException(413,"单次打包最多500 MB，请分批下载")
                path=folder/str(len(staged));os.link(storage.file_path(item),path)
                name=storage.safe_name(work.title)[:100]+"-"+work.id[:8]+"/"+a.role+"-"+storage.safe_name(a.filename)
                staged.append((path,name))
        db.rollback()
        target=folder/"works.zip"
        with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            for path,name in staged:z.write(path,name);path.unlink()
        return FileResponse(target,media_type="application/zip",filename="教学作品.zip",background=BackgroundTask(shutil.rmtree,folder,ignore_errors=True),headers={"Cache-Control":"no-store"})
    except BaseException:
        if folder:shutil.rmtree(folder,ignore_errors=True)
        raise
    finally:zip_slots.release()

@router.get("/manage/zip-file")
def download_zip_file(item:list[str]=Query(...,min_length=1,max_length=100),db:Session=Depends(get_db),user:User=Depends(current_user)):
    choices=[]
    for value in item:
        ident,sep,version=value.partition(":")
        if not sep or not re.fullmatch(r"[0-9a-f-]{36}",ident) or not version.isdigit() or len(version)>10:
            raise HTTPException(422,"下载选项无效")
        choices.append(WorkChoice(id=ident,version=int(version)))
    return download_zip(Choices(items=choices),db,user)


def cleanup_stale_zips():
    # Normal responses remove their folder immediately. Recover interrupted downloads
    # after a full day; never remove a folder while it is being built.
    if not zip_slots.acquire(blocking=False):
        return
    try:
        for folder in storage.root().glob("work-zip-*"):
            if folder.is_dir() and not folder.is_symlink() and time.time()-folder.stat().st_mtime>86400:
                shutil.rmtree(folder,ignore_errors=True)
    finally:
        zip_slots.release()
