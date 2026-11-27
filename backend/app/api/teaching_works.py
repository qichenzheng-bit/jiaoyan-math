"""Read-only authenticated work catalogue foundation."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import current_user
from app.models import User, TeachingWork, TeachingWorkVersion, TeachingWorkAsset, StoredFile
from app.services import storage

router = APIRouter(prefix="/teaching-works", tags=["teaching-works"], dependencies=[Depends(current_user)])


def summary(work):
    return {key: getattr(work, key) for key in ("id", "title", "kind", "subject", "origin_scope",
            "origin_id", "current_version", "created_at", "updated_at")}


def owned(db, user, ident):
    work = db.scalar(select(TeachingWork).where(TeachingWork.id == ident, TeachingWork.user_id == user.id))
    if work is None:
        raise HTTPException(404, "作品不存在")
    return work


@router.get("")
def listing(q: str = Query("", max_length=200), kind: str = Query("", max_length=20),
            offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(TeachingWork).where(TeachingWork.user_id == user.id)
    if q.strip():
        stmt = stmt.where(TeachingWork.title.contains(q.strip(), autoescape=True))
    if kind:
        stmt = stmt.where(TeachingWork.kind == kind)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(TeachingWork.updated_at.desc(), TeachingWork.id).offset(offset).limit(limit))
    return {"items": [summary(w) for w in rows], "total": total}


@router.get("/{ident}")
def detail(ident: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    work = owned(db, user, ident)
    versions = list(db.scalars(select(TeachingWorkVersion).where(
        TeachingWorkVersion.work_id == work.id).order_by(TeachingWorkVersion.number.desc())))
    assets = list(db.execute(select(TeachingWorkAsset, StoredFile).join(
        StoredFile, StoredFile.id == TeachingWorkAsset.file_id).where(TeachingWorkAsset.work_id == work.id)))
    return {**summary(work), "versions": [
        {"number": v.number, "created_at": v.created_at, "files": [
            {"role": a.role, "filename": a.filename, "pages": a.pages,
             "size_bytes": f.size_bytes, "media_type": f.media_type}
            for a, f in assets if a.version == v.number]}
        for v in versions]}


@router.get("/{ident}/versions/{number}/files/{role}")
def read_file(ident: str, number: int, role: str, download: bool = False,
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    work = owned(db, user, ident)
    asset = db.get(TeachingWorkAsset, (work.id, number, role))
    if asset is None:
        raise HTTPException(404, "成品文件不存在")
    item = db.get(StoredFile, asset.file_id)
    return FileResponse(storage.file_path(item), media_type=item.media_type, filename=asset.filename,
                        content_disposition_type="attachment" if download else "inline",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
