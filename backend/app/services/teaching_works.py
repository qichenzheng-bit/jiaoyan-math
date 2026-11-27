"""Durable PDF catalogue and reference-aware generated-file retirement."""
import hashlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select, text, or_
from sqlalchemy.orm import Session

from app.core.security import now, audit
from app.models import (User, StoredFile, FileReference, TeachingWork,
                        TeachingWorkVersion, TeachingWorkAsset, TeachingWorkPendingCover)
from app.services import storage
from app.services.inline_images import image_ids

OWNER = "teaching_work_version"
PENDING = "teaching_work_pending_cover"
RETIRE_GRACE = 3600


def digest_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def version_owner(work_id, number):
    return f"{work_id}:{number}"


def context(payload):
    """Server-derived logical edition and body fingerprint, also used for wrap exports."""
    doc = payload["doc"]
    variant = {"stem": bool(payload.get("stem")), "answerOnly": bool(payload.get("answerOnly")),
               "chapter": payload.get("chapter_uid") or doc.get("export_chapter_uid"),
               "selection": sorted(payload["selected_uids"]) if payload.get("selected_uids") is not None else None,
               "page_ranges": payload.get("page_ranges", "").strip()}
    fingerprint = digest_json({"blocks": doc.get("blocks", []), "title": doc.get("title"),
                               "layout": payload["layout"], "variant": variant})
    return {"variant": digest_json(variant), "fingerprint": fingerprint, "edition": variant}


def store_pdf(db, path: Path, filename: str, digest: str):
    if storage.detect_type(path, filename) != "application/pdf":
        raise ValueError("not a PDF")
    existing = db.scalar(select(StoredFile).where(
        StoredFile.sha256 == digest, StoredFile.generated == True,
        StoredFile.purged_at.is_(None), StoredFile.media_type == "application/pdf",
    ).order_by(StoredFile.created_at, StoredFile.id).limit(1).with_for_update())
    if existing:
        storage.file_path(existing)
        existing.archived = False
        existing.work_retired_at = None
        return existing
    fid = str(uuid4())
    key = "generated/" + fid
    target = storage.root() / key
    target.parent.mkdir(mode=0o700, exist_ok=True)
    os.link(path, target)
    item = StoredFile(id=fid, sha256=digest, name=filename, storage_key=key,
                      size_bytes=path.stat().st_size, media_type="application/pdf",
                      generated=True, archived=False, created_at=now(), work_managed=True)
    db.add(item)
    db.flush()
    return item


def trim_versions(db: Session, work: TeachingWork):
    versions = list(db.scalars(select(TeachingWorkVersion).where(
        TeachingWorkVersion.work_id == work.id
    ).order_by(TeachingWorkVersion.number.desc())))
    for old in versions[2:]:
        db.execute(delete(FileReference).where(
            FileReference.owner_type == OWNER,
            FileReference.owner_id == version_owner(work.id, old.number)))
        db.execute(delete(TeachingWorkAsset).where(
            TeachingWorkAsset.work_id == work.id, TeachingWorkAsset.version == old.number))
        db.delete(old)


def remove_pending(db, pending):
    if pending:
        db.execute(delete(FileReference).where(FileReference.owner_type == PENDING,
                                              FileReference.owner_id == pending.work_id))
        db.delete(pending)
        db.flush()


def append_version(db, work, fingerprint, snapshot, assets):
    number = work.current_version + 1
    db.add(TeachingWorkVersion(work_id=work.id, number=number, fingerprint=fingerprint,
                               snapshot=snapshot, facets=snapshot.get("facets", {}), created_at=now()))
    db.flush()
    for role, fid, filename, pages in assets:
        db.add(TeachingWorkAsset(work_id=work.id, version=number, role=role,
                                 file_id=fid, filename=filename, pages=pages))
        storage.link_file(db, fid, OWNER, version_owner(work.id, number))
    protect_snapshot_images(db, work.id, number, snapshot)
    work.current_version = number
    work.updated_at = now()
    db.flush()
    trim_versions(db, work)
    return work.id, number


def protect_snapshot_images(db, work_id, number, snapshot):
    ids = set(snapshot.get("image_ids", []))
    layout = snapshot.get("layout", {})
    ids.update(fid for fid in (layout.get("coverFileId"), layout.get("backCoverFileId")) if fid)
    for block in snapshot.get("doc", {}).get("blocks", []):
        if block.get("kind") == "image" and block.get("file_id"):
            ids.add(block["file_id"])
        ids.update(image_ids(block))
        ids.update(image_ids(block.get("snapshot") or {}))
    # Existing archived originals can be protected without unarchiving them.
    # Purged legacy originals cannot be recreated; keep the already rendered PDF usable.
    for fid in sorted(ids):
        item = db.scalar(select(StoredFile).where(StoredFile.id == fid).with_for_update())
        if item and item.purged_at is None and item.media_type in storage.IMAGE_TYPES:
            key = (fid, OWNER, version_owner(work_id, number))
            if db.get(FileReference, key) is None:
                db.add(FileReference(file_id=fid, owner_type=OWNER, owner_id=key[2]))


def restore_version(db, *, user_id, work_id, number, expected):
    from fastapi import HTTPException
    if not db.scalar(select(User.id).where(User.id == user_id).with_for_update()):
        raise HTTPException(404, "用户不存在")
    work = db.scalar(select(TeachingWork).where(
        TeachingWork.id == work_id, TeachingWork.user_id == user_id).with_for_update())
    if not work:
        raise HTTPException(404, "作品不存在")
    if work.current_version != expected:
        raise HTTPException(409, "作品版本已经变化，请刷新后重试")
    old = db.get(TeachingWorkVersion, (work.id, number))
    if not old:
        raise HTTPException(404, "历史版本已清理")
    if number == expected:
        return work.id, expected
    assets = list(db.scalars(select(TeachingWorkAsset).where(
        TeachingWorkAsset.work_id == work.id, TeachingWorkAsset.version == number)))
    if not any(a.role == "body" for a in assets):
        raise HTTPException(409, "历史正文缺失")
    for a in assets:
        storage.file_path(db.get(StoredFile, a.file_id))
    result = append_version(db, work, old.fingerprint, {**old.snapshot, "restored_from": number},
                            [asset_tuple(a) for a in assets])
    audit(db, "teaching_work.restore", user_id)
    return result


def asset_tuple(asset):
    return asset.role, asset.file_id, asset.filename, asset.pages


def register_pdf(db: Session, *, user_id: int, scope: str, identity: str,
                 filename: str, path: Path, payload: dict, pages: int):
    """Register a rendered edition. A return version of zero means a pending cover."""
    if scope not in ("doc", "source") or not path.is_file() or pages < 1:
        raise ValueError("not a rendered PDF")
    filename = storage.safe_name(filename)
    doc = payload["doc"]
    if not db.scalar(select(User.id).where(User.id == user_id).with_for_update()):
        raise ValueError("unknown owner")
    if payload.get("wrap") and not payload.get("work_context"):
        raise ValueError("legacy wrap snapshot cannot be safely matched")
    ctx = payload.get("work_context") or context(payload)
    variant, fingerprint = ctx["variant"], ctx["fingerprint"]
    edition = ctx["edition"]
    snapshot = {"doc": doc, "layout": payload["layout"], "edition": edition,
                "stem": bool(payload.get("stem")), "answerOnly": bool(payload.get("answerOnly")),
                "overrides": payload.get("overrides", {}), "image_ids": payload.get("snapshot_image_ids", []),
                "facets": payload.get("work_facets", {})}
    work = db.scalar(select(TeachingWork).where(
        TeachingWork.user_id == user_id, TeachingWork.origin_scope == scope,
        TeachingWork.origin_id == identity, TeachingWork.variant == variant
    ).with_for_update())
    if not work:
        kind = "source" if scope == "source" else str(doc.get("kind") or "document")[:20]
        title = str(doc.get("title") or Path(filename).stem)
        labels = []
        if edition.get("chapter"): labels.append("章节")
        if edition.get("selection") is not None: labels.append("选取内容")
        if edition.get("page_ranges"): labels.append("指定页")
        if edition.get("stem"): labels.append("题目版")
        if edition.get("answerOnly"): labels.append("答案版")
        title = title + ("（" + "·".join(labels) + "）" if labels else "")
        work = TeachingWork(id=str(uuid4()), user_id=user_id, origin_scope=scope,
                            origin_id=identity, variant=variant, kind=kind, title=title[:200],
                            subject=str(doc.get("subject") or "")[:40],
                            current_version=0, created_at=now(), updated_at=now())
        db.add(work)
        db.flush()
    current = db.get(TeachingWorkVersion, (work.id, work.current_version)) if work.current_version else None
    body = db.get(TeachingWorkAsset, (work.id, work.current_version, "body")) if current else None
    cover = db.get(TeachingWorkAsset, (work.id, work.current_version, "cover")) if current else None
    pending = db.get(TeachingWorkPendingCover, work.id)
    matching = bool(current and body and current.fingerprint == fingerprint)

    if payload.get("wrap"):
        wrap = payload["wrap"]
        if matching and cover and current.snapshot.get("wrap") == wrap:
            storage.file_path(db.get(StoredFile, cover.file_id))
            return work.id, work.current_version
        if not matching and pending and pending.fingerprint == fingerprint and pending.snapshot.get("wrap") == wrap:
            storage.file_path(db.get(StoredFile, pending.file_id))
            return work.id, 0
        item = store_pdf(db, path, filename, file_digest(path))
        if matching:
            result = append_version(db, work, fingerprint, {**current.snapshot, "wrap": wrap},
                                    [asset_tuple(body), ("cover", item.id, filename, pages)])
            if pending and pending.fingerprint == fingerprint:
                remove_pending(db, pending)
        else:
            remove_pending(db, pending)
            db.add(TeachingWorkPendingCover(work_id=work.id, fingerprint=fingerprint,
                    file_id=item.id, filename=filename, snapshot={"wrap": wrap}, created_at=now()))
            storage.link_file(db, item.id, PENDING, work.id)
            work.updated_at = now()
            result = work.id, 0
    else:
        matching_pending = pending is not None and pending.fingerprint == fingerprint
        if matching and not matching_pending:
            storage.file_path(db.get(StoredFile, body.file_id))
            return work.id, work.current_version
        assets = [asset_tuple(body)] if matching else [
            ("body", store_pdf(db, path, filename, file_digest(path)).id, filename, pages)]
        if matching_pending:
            assets.append(("cover", pending.file_id, pending.filename, 1))
            snapshot["wrap"] = pending.snapshot["wrap"]
        elif matching and cover:
            assets.append(asset_tuple(cover))
            snapshot["wrap"] = current.snapshot["wrap"]
        result = append_version(db, work, fingerprint, snapshot, assets)
        if matching_pending:
            remove_pending(db, pending)
    audit(db, "teaching_work.register_pdf", user_id)
    return result


def retire_files(db: Session, limit=50):
    """Only registry-owned generated files; wait a grace period, respect backup lock.

    A durable tombstone precedes unlink. File rows remain for historical metadata.
    """
    if db.bind.dialect.name == "postgresql":
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": storage.PURGE_LOCK}):
            db.rollback()
            return 0
    unused = ~select(FileReference.file_id).where(FileReference.file_id == StoredFile.id).exists()
    candidates = list(db.scalars(select(StoredFile).where(
        StoredFile.work_managed == True, StoredFile.generated == True,
        or_(StoredFile.purge_pending == True, (StoredFile.purged_at.is_(None) & unused))
    ).order_by(StoredFile.work_retired_at.asc().nulls_last(), StoredFile.id).limit(limit).with_for_update(skip_locked=True)))
    pending = []
    for f in candidates:
        if storage.reference_count(db, f.id) or db.scalar(select(TeachingWorkAsset.file_id).where(
                TeachingWorkAsset.file_id == f.id).limit(1)) or db.scalar(select(TeachingWorkPendingCover.file_id).where(
                TeachingWorkPendingCover.file_id == f.id).limit(1)):
            f.work_retired_at = None
            continue
        if f.purge_pending:
            pending.append(f.id)
        elif f.work_retired_at is None:
            f.work_retired_at = now()
        elif now() - f.work_retired_at >= RETIRE_GRACE:
            f.archived = True
            f.purged_at = now()
            f.purge_pending = True
            pending.append(f.id)
    db.commit()
    removed = 0
    for fid in pending:
        f = db.scalar(select(StoredFile).where(StoredFile.id == fid).with_for_update())
        if not f or not f.work_managed or not f.generated or not f.purge_pending or f.purged_at is None:
            db.rollback()
            continue
        try:
            if not re.fullmatch(r"[0-9a-f-]{36}", fid) or f.storage_key != "generated/" + fid:
                raise ValueError("invalid managed key")
            base = storage.root()
            folder = base / "generated"
            path = folder / fid
            if folder.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(base):
                raise ValueError("unsafe managed path")
            path.unlink(missing_ok=True)
        except (OSError, ValueError):
            db.rollback()
            continue
        f.purge_pending = False
        db.commit()
        removed += 1
    return removed
