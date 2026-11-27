"""Authenticated finished works catalogue. Videos remain in the existing engine."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func, literal, cast, Integer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import current_user
from app.models import (User, TeachingWork, TeachingWorkVersion, TeachingWorkAsset,
                        TeachingWorkPendingCover, StoredFile, StudioItem, VideoProject)
from app.services import storage

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


@router.get("")
def listing(q: str = Query("", max_length=200), kind: str = Query("", max_length=20),
            subject: str = Query("", max_length=40),
            scope: Literal["", "doc", "source", "video"] = "",
            sort: Literal["recent", "old", "name"] = "recent",
            created_from: int | None = Query(None, ge=0),
            created_to: int | None = Query(None, ge=0),
            offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), user: User = Depends(current_user)):
    docs = select(*(getattr(TeachingWork, key).label(key) for key in FIELDS)).where(
        TeachingWork.user_id == user.id)
    combined = docs.union_all(video_records(user)).subquery()
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
        return {**dict(found), "versions": [], "pending_cover": None,
                "video": {"project_id": project.id, "resource_id": project.resource_id,
                          "cover_file_id": cover, "revision_managed_by_engine": True}}
    # Do not load complete document snapshots in the file/detail request.
    versions = db.execute(select(TeachingWorkVersion.number, TeachingWorkVersion.created_at).where(
        TeachingWorkVersion.work_id == work.id).order_by(TeachingWorkVersion.number.desc())).all()
    assets = list(db.execute(select(TeachingWorkAsset, StoredFile).join(
        StoredFile, StoredFile.id == TeachingWorkAsset.file_id).where(TeachingWorkAsset.work_id == work.id)))
    pending = db.execute(select(TeachingWorkPendingCover.filename, TeachingWorkPendingCover.created_at).where(
        TeachingWorkPendingCover.work_id == work.id)).first()
    return {**summary(work), "pending_cover": {"filename":pending.filename,"created_at":pending.created_at} if pending else None,
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
            "partial_pages": bool(version.snapshot.get("edition", {}).get("page_ranges"))}


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
