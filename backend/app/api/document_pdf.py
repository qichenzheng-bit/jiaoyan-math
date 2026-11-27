"""Private, bounded PDF jobs. Rendering uses only validated server document snapshots."""
import json
import logging
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.api.documents import source_export, export_document, check_complete_export_size
from app.api.settings import DocumentLayout
from app.core.db import get_db
from app.core.security import current_user, require_origin
from app.models import User, StoredFile
from app.services import storage
from app.services.document_pdf import render_pdf
from app.services.inline_images import image_ids

router = APIRouter(prefix="/document-pdf", tags=["document-pdf"], dependencies=[Depends(current_user)])
logger = logging.getLogger(__name__)
lock = threading.RLock()
pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wg-pdf")
jobs = {}
TERMINAL = {"ready", "failed", "cancelled"}
TTL = 6 * 3600

class LocalEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=50000)
    answer: str | None = Field(default=None, max_length=20000)
    solution: str | None = Field(default=None, max_length=50000)
    analysis: str | None = Field(default=None, max_length=50000)
    proof: str | None = Field(default=None, max_length=50000)

class PdfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    export_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    layout: DocumentLayout
    stem: bool = False
    answerOnly: bool = False
    selected_uids: list[str] | None = Field(default=None, max_length=5100)
    overrides: dict[str, LocalEdit] = Field(default_factory=dict, max_length=5100)
    chapter_uid: str | None = Field(default=None, max_length=100)
    filename: str = Field(min_length=1, max_length=200)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def check_selection(self):
        if self.selected_uids is not None and (not self.selected_uids or len(set(self.selected_uids)) != len(self.selected_uids)):
            raise ValueError("导出内容为空或编号重复")
        if any(len(uid) > 100 for uid in (self.selected_uids or []) + list(self.overrides)):
            raise ValueError("内容编号无效")
        return self

@dataclass
class Job:
    id: str
    user_id: int
    scope: str
    identity: str
    filename: str
    directory: tempfile.TemporaryDirectory
    images: dict
    state: str = "queued"
    stage: str = "等待生成"
    detail: str = ""
    pages: int = 0
    bytes: int = 0
    changed: float = field(default_factory=time.monotonic)
    stop: threading.Event = field(default_factory=threading.Event)

    @property
    def output(self):
        return Path(self.directory.name) / "result.pdf"

    @property
    def payload(self):
        return Path(self.directory.name) / "payload.json"

    def view(self):
        return {"id": self.id, "state": self.state, "stage": self.stage, "detail": self.detail,
                "filename": self.filename, "pages": self.pages, "bytes": self.bytes}

def cleanup():
    # Caller holds lock. Never remove data from a running render.
    stale = [key for key, job in jobs.items() if job.state in TERMINAL and time.monotonic() - job.changed > TTL]
    for key in stale:
        jobs.pop(key).directory.cleanup()

def change(job, **fields):
    with lock:
        for key, value in fields.items():
            setattr(job, key, value)
        job.changed = time.monotonic()

def run(job):
    try:
        if job.stop.is_set():
            change(job, state="cancelled", stage="已取消")
            return
        change(job, state="running", stage="读取排版快照")
        result = render_pdf(job.payload, job.images, job.output,
                            lambda stage: change(job, stage=stage), job.stop.is_set)
        if job.stop.is_set() or result is None:
            job.output.unlink(missing_ok=True)
            change(job, state="cancelled", stage="已取消")
        else:
            change(job, state="ready", stage="生成完成", pages=result["pages"], bytes=result["bytes"])
    except ValueError as exc:
        job.output.unlink(missing_ok=True)
        change(job, state="failed", stage="排版检查失败", detail=str(exc)[:300])
    except Exception as exc:
        logger.error("PDF generation failed: %s", type(exc).__name__)
        job.output.unlink(missing_ok=True)
        change(job, state="failed", stage="生成失败", detail="PDF 渲染环境或文件异常，请重试或联系管理员检查浏览器服务。")
    finally:
        job.payload.unlink(missing_ok=True)
        job.images.clear()

def get_job(user, job_id):
    cleanup()
    job = jobs.get(job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "生成记录不存在或已过期")
    return job

def build_snapshot(scope, identity, request, db):
    data = source_export(identity, db) if scope == "source" else export_document(identity, db)
    if data["export_token"] != request.export_token:
        raise HTTPException(409, "资料在预览后发生变化，请重新打开并检查排版")
    blocks = data["blocks"]
    if request.chapter_uid:
        start = next((i for i, b in enumerate(blocks) if b["uid"] == request.chapter_uid and b["kind"] == "heading" and b.get("heading_level") == 1), None)
        if start is None:
            raise HTTPException(422, "未找到选定章节")
        end = next((i for i in range(start+1, len(blocks)) if blocks[i]["kind"] == "heading" and blocks[i].get("heading_level") == 1), len(blocks))
        blocks = blocks[start:end]
    valid = {b["uid"] for b in blocks}
    if not set(request.overrides) <= valid or request.selected_uids is not None and not set(request.selected_uids) <= valid:
        raise HTTPException(422, "选取内容已失效，请刷新资料")
    if request.selected_uids is not None:
        selected = set(request.selected_uids)
        blocks = [b for b in blocks if b["uid"] in selected]
    if not blocks:
        raise HTTPException(422, "请选择需要导出的内容")
    if scope != "source" and request.overrides:
        raise HTTPException(422, "自编资料内容请在编排工作台修改")
    result = []
    for block in blocks:
        edit = request.overrides.get(block["uid"])
        if edit:
            fields = edit.model_dump(exclude_none=True)
            block = {**block, **fields, "local_fields": sorted(set(block.get("local_fields") or []) | set(fields))}
        result.append(block)
    return {**data, "blocks": result}

def resolve_images(db, data):
    ids = set()
    for block in data["blocks"]:
        if block.get("kind") == "image" and block.get("file_id"):
            ids.add(block["file_id"])
        ids.update(image_ids(block))
        ids.update(image_ids(block.get("snapshot") or {}))
    images = {}
    for fid in ids:
        item = db.get(StoredFile, fid)
        if item is None or item.media_type not in storage.IMAGE_TYPES:
            raise HTTPException(422, "图片不存在或格式不受支持")
        images["/api/files/" + fid + "/preview"] = (str(storage.file_path(item)), item.media_type)
    return images

@router.post("/{scope}/{identity}", dependencies=[Depends(require_origin)])
def create_pdf(scope: Literal["source", "doc"], identity: str, body: PdfRequest,
               db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = build_snapshot(scope, identity, body, db)
    images = resolve_images(db, data)
    payload = {"doc": data, "layout": body.layout.model_dump(), "stem": body.stem,
               "answerOnly": body.answerOnly, "source": scope == "source"}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    check_complete_export_size(len(raw))
    filename = storage.safe_name(body.filename.strip().removesuffix(".pdf") + ".pdf")
    with lock:
        cleanup()
        active = [job for job in jobs.values() if job.state not in TERMINAL]
        if len(active) >= 2:
            raise HTTPException(429, "PDF 生成队列已满，请稍后重试")
        if len(jobs) >= 12:
            raise HTTPException(429, "请先清理已生成的临时 PDF")
        folder = tempfile.TemporaryDirectory(prefix="wg-layout-pdf-")
        job = Job(str(uuid4()), user.id, scope, identity, filename, folder, images)
        try:
            job.payload.write_bytes(raw)
            jobs[job.id] = job
            pool.submit(run, job)
        except Exception:
            jobs.pop(job.id, None)
            folder.cleanup()
            raise
        return job.view()

@router.get("/{scope}/{identity}/jobs")
def list_pdf_jobs(scope: Literal["source", "doc"], identity: str, user: User = Depends(current_user)):
    with lock:
        cleanup()
        return [j.view() for j in reversed(list(jobs.values())) if j.user_id == user.id and j.scope == scope and j.identity == identity]

@router.get("/jobs/{job_id}/status")
def status_pdf(job_id: str, user: User = Depends(current_user)):
    with lock:
        return get_job(user, job_id).view()

@router.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_origin)])
def cancel_pdf(job_id: str, user: User = Depends(current_user)):
    with lock:
        job = get_job(user, job_id)
        if job.state not in TERMINAL:
            job.stop.set()
            change(job, stage="正在取消")
        return job.view()

@router.delete("/jobs/{job_id}", dependencies=[Depends(require_origin)])
def delete_pdf(job_id: str, user: User = Depends(current_user)):
    with lock:
        job = get_job(user, job_id)
        if job.state not in TERMINAL:
            raise HTTPException(409, "请先取消生成任务")
        jobs.pop(job.id)
        job.directory.cleanup()
        return {"deleted": True}

@router.get("/jobs/{job_id}/file")
def pdf_file(job_id: str, download: bool = False, user: User = Depends(current_user)):
    with lock:
        job = get_job(user, job_id)
        if job.state != "ready" or not job.output.is_file():
            raise HTTPException(409, "PDF 尚未生成")
        return FileResponse(job.output, media_type="application/pdf", filename=job.filename,
                            content_disposition_type="attachment" if download else "inline",
                            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
