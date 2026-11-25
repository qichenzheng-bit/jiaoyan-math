from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.core.db import get_db, session_factory
from app.core.security import audit, current_user, require_origin
from app.models import StoredFile, User
from app.services import storage

router = APIRouter(prefix="/files", tags=["files"], dependencies=[Depends(current_user)])

@router.get("")
def list_files(db: Session = Depends(get_db), archived: bool = False,
               offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    query = select(StoredFile).where(StoredFile.archived == archived)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(StoredFile.created_at.desc(), StoredFile.id).offset(offset).limit(limit))
    return {"items": [storage.serialize(item) for item in rows], "total": total}

@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    count, size = db.execute(select(func.count(), func.coalesce(func.sum(StoredFile.size_bytes), 0))).one()
    return {"count": count, "bytes": size, "max_file_bytes": settings.max_file_bytes}

@router.post("", dependencies=[Depends(require_origin)])
async def upload(request: Request, name: str = Query(min_length=1, max_length=255), user: User = Depends(current_user)):
    name = storage.safe_name(name)
    length = request.headers.get("content-length")
    if length and (not length.isdecimal() or int(length) > settings.max_file_bytes):
        raise HTTPException(413, "文件超过大小限制")
    temp = await run_in_threadpool(storage.new_stage)
    size = 0
    try:
        with temp.open("wb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > settings.max_file_bytes:
                    raise HTTPException(413, "文件超过大小限制")
                await run_in_threadpool(handle.write, chunk)
        def persist():
            with session_factory()() as db:
                return storage.save_staged(db, temp, name, user.id)
        return await run_in_threadpool(persist)
    finally:
        temp.unlink(missing_ok=True)

def find_file(file_id: str, db: Session) -> StoredFile:
    item = db.get(StoredFile, file_id)
    if item is None:
        raise HTTPException(404, "文件不存在")
    return item

@router.get("/{file_id}/download")
def download(file_id: str, db: Session = Depends(get_db)):
    item = find_file(file_id, db)
    return FileResponse(storage.file_path(item), filename=item.name, media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})

@router.get("/{file_id}/preview")
def preview(file_id: str, db: Session = Depends(get_db)):
    item = find_file(file_id, db)
    if item.media_type not in storage.IMAGE_TYPES:
        raise HTTPException(415, "此文件仅支持下载")
    return FileResponse(storage.file_path(item), media_type=item.media_type,
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'"})

@router.post("/{file_id}/archive", dependencies=[Depends(require_origin)])
def archive(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(StoredFile).where(StoredFile.id == file_id).with_for_update())
    if item is None:
        raise HTTPException(404, "文件不存在")
    if storage.reference_count(db, file_id):
        raise HTTPException(409, "文件仍被其他资源引用")
    item.archived = True
    audit(db, "file.archive", user.id)
    db.commit()
    return storage.serialize(item)

@router.post("/{file_id}/restore", dependencies=[Depends(require_origin)])
def restore(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = find_file(file_id, db)
    item.archived = False
    audit(db, "file.restore", user.id)
    db.commit()
    return storage.serialize(item)
