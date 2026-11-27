"""Private storage: original files and generated artifacts have separate roots."""
import hashlib
import os
import re
import tempfile
import uuid
import zipfile
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import audit, now
from app.models import StoredFile, FileReference, User

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
TEXT_TYPES = {".txt": "text/plain", ".tex": "text/plain", ".md": "text/plain", ".csv": "text/csv"}
OFFICE_TYPES = {
    ".docx": ("word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": ("xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".pptx": ("ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
}

def root() -> Path:
    if not settings.storage_root or not Path(settings.storage_root).is_absolute():
        raise HTTPException(503, "文件存储尚未配置")
    path = Path(settings.storage_root).resolve()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path

def safe_name(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."} or len(name) > 255 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise HTTPException(400, "文件名无效")
    return name

def detect_type(path: Path, name: str) -> str:
    ext = Path(name).suffix.lower()
    with path.open("rb") as handle:
        head = handle.read(16)
    if ext == ".png" and head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if ext in {".jpg", ".jpeg"} and head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if ext == ".webp" and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if ext == ".gif" and head[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if ext == ".pdf" and head.startswith(b"%PDF-"):
        return "application/pdf"
    if ext in TEXT_TYPES:
        try:
            data = path.read_text(encoding="utf-8-sig")
            if "\x00" in data:
                raise ValueError("binary")
            return TEXT_TYPES[ext]
        except (UnicodeError, ValueError):
            pass
    if ext in OFFICE_TYPES and zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                marker, media = OFFICE_TYPES[ext]
                if (len(entries) <= 10000 and sum(e.file_size for e in entries) <= 200 * 1024 * 1024
                        and marker in names and "[Content_Types].xml" in names
                        and not any("vbaproject" in n.lower() or n.startswith("/") or ".." in n.split("/") for n in names)):
                    return media
        except (zipfile.BadZipFile, OSError):
            pass
    raise HTTPException(415, "不支持此格式或文件内容与扩展名不符")

def file_path(item: StoredFile) -> Path:
    if item.purged_at is not None:raise HTTPException(410, "原始文件已永久清理，历史录入记录仍保留")
    base = root()
    path = (base / item.storage_key).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise HTTPException(404, "文件内容不存在")
    return path

def serialize(item: StoredFile, duplicate: bool = False) -> dict:
    return {"id": item.id, "name": item.name, "size_bytes": item.size_bytes,
            "media_type": item.media_type, "sha256": item.sha256,
            "generated": item.generated, "archived": item.archived,
            "created_at": item.created_at, "duplicate": duplicate,
            "purged_at": item.purged_at, "purge_pending": item.purge_pending,
            "previewable": item.media_type in IMAGE_TYPES and item.purged_at is None}

def save_staged(db: Session, temp: Path, name: str, user_id: int, generated: bool = False) -> dict:
    name = safe_name(name)
    size = temp.stat().st_size
    if size == 0 or size > settings.max_file_bytes:
        raise HTTPException(413, "文件为空或超过大小限制")
    media = detect_type(temp, name)
    hasher = hashlib.sha256()
    with temp.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    # Serialize deduplication across workers with the single administrator row.
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    existing = db.scalar(select(StoredFile).where(StoredFile.sha256 == digest, StoredFile.generated == generated, StoredFile.purged_at.is_(None)).order_by(StoredFile.created_at))
    if existing and file_path(existing).is_file():
        if existing.archived:
            existing.archived = False
            audit(db, "file.restore", user_id)
        db.commit()
        return serialize(existing, duplicate=True)
    identifier = str(uuid.uuid4())
    key = ("generated/" if generated else "original/") + identifier
    target = root() / key
    target.parent.mkdir(mode=0o700, exist_ok=True)
    os.replace(temp, target)
    item = StoredFile(id=identifier, sha256=digest, name=name, storage_key=key,
        size_bytes=size, media_type=media, generated=generated, archived=False, created_at=now())
    try:
        db.add(item)
        audit(db, "file.upload", user_id)
        db.commit()
    except Exception:
        db.rollback()
        # Keep an orphan on ambiguous commit failure; reconciliation is safer than data loss.
        raise
    return serialize(item)

def new_stage() -> Path:
    stage = root() / ".staging"
    stage.mkdir(mode=0o700, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=stage)
    os.close(descriptor)
    return Path(name)

def reference_count(db: Session, file_id: str) -> int:
    return db.scalar(select(func.count()).select_from(FileReference).where(FileReference.file_id == file_id)) or 0

def link_file(db: Session, file_id: str, owner_type: str, owner_id: str):
    """Called within a future resource/work transaction, not a public API."""
    item = db.scalar(select(StoredFile).where(StoredFile.id == file_id).with_for_update())
    if item is None or item.archived or item.purged_at is not None:
        raise HTTPException(404, "文件不存在或已归档")
    # A new reference cancels a pending retirement before its grace period expires.
    item.work_retired_at = None
    key = (file_id, owner_type, owner_id)
    if db.get(FileReference, key) is None:
        db.add(FileReference(file_id=file_id, owner_type=owner_type, owner_id=owner_id))

# Stable PostgreSQL advisory lock shared with deploy/backup.py. No snapshot may read a blob while it is being purged.
PURGE_LOCK = 824650219
def remove_purged_original(item: StoredFile):
    if item.purged_at is None or not item.archived or item.generated:
        raise ValueError("file not marked for purge")
    if not re.fullmatch(r"[0-9a-f-]{36}",item.id) or item.storage_key!="original/"+item.id:
        raise ValueError("invalid original storage key")
    base=root()
    folder=base/"original"
    path=folder/item.id
    # Refuse symlinks and unexpected storage layout even when retrying a missing file.
    if folder.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(base):
        raise ValueError("unsafe original path")
    path.unlink(missing_ok=True)
