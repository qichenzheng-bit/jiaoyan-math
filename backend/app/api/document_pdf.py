"""Private, bounded PDF jobs. Rendering uses only validated server document snapshots."""
import json
import logging
import asyncio
import os
import re
import shutil
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
from app.core.db import get_db, session_factory
from app.core.config import settings
from app.core.security import current_user, require_origin
from app.models import User, StoredFile
from app.services import storage, teaching_works
from app.services.document_pdf import render_pdf, selected_pages
from app.services.inline_images import image_ids

router = APIRouter(prefix="/document-pdf", tags=["document-pdf"], dependencies=[Depends(current_user)])
logger = logging.getLogger(__name__)
lock = threading.RLock()
pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wg-pdf")
jobs = {}
loaded_root: Path | None = None
queue_lock = None
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

class PrintWrap(BaseModel):
    model_config=ConfigDict(extra="forbid")
    spine: float=Field(ge=0,le=150)
    bleed: float=Field(ge=0,le=20)
    spineText: str=Field(default="",max_length=200)
    background: str=Field(default="#ffffff",pattern=r"^#[0-9a-fA-F]{6}$")
    foreground: str=Field(default="#222222",pattern=r"^#[0-9a-fA-F]{6}$")

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
    page_ranges: str = Field(default="", max_length=2000)
    preview_pages: int | None = Field(default=None, ge=1, le=10000)
    wrap: PrintWrap|None=None
    confirmed: Literal[True]

    @model_validator(mode="after")
    def check_selection(self):
        if self.selected_uids is not None and (not self.selected_uids or len(set(self.selected_uids)) != len(self.selected_uids)):
            raise ValueError("导出内容为空或编号重复")
        if any(len(uid) > 100 for uid in (self.selected_uids or []) + list(self.overrides)):
            raise ValueError("内容编号无效")
        if self.wrap:
            if self.page_ranges.strip() or not self.layout.coverFileId or not self.layout.backCoverFileId or self.layout.sectionPages:
                raise ValueError("书衣须使用统一开本与完整封面封底，不支持指定页码")
            if self.wrap.spineText.strip() and self.wrap.spine<4:raise ValueError("书脊宽度不足")
        if self.page_ranges.strip():
            if self.preview_pages is None:raise ValueError("请先计算完整预览页数")
            selected_pages(self.page_ranges,self.preview_pages)
        return self

@dataclass
class Job:
    id: str
    user_id: int
    scope: str
    identity: str
    filename: str
    directory: Path
    images: dict
    state: str = "queued"
    stage: str = "等待生成"
    detail: str = ""
    pages: int = 0
    bytes: int = 0
    total_pages: int = 0
    page_ranges: str = ""
    changed: float = field(default_factory=time.time)
    stop: threading.Event = field(default_factory=threading.Event)
    work_id: str | None = None
    work_version: int | None = None
    work_error: str = ""

    @property
    def output(self):
        return self.directory / "result.pdf"

    @property
    def payload(self):
        return self.directory / "payload.json"

    def view(self):
        return {"id": self.id, "state": self.state, "stage": self.stage, "detail": self.detail,
                "filename": self.filename, "pages": self.pages, "bytes": self.bytes, "total_pages": self.total_pages, "page_ranges":self.page_ranges,
                "work_id":self.work_id,"work_version":self.work_version,"work_error":self.work_error}

def persist(job):
    """Only server-created files and validated snapshots enter the private queue."""
    images={key:[str(Path(value[0]).relative_to(job.directory)),value[1]] for key,value in job.images.items()}
    value={**job.view(),"user_id":job.user_id,"scope":job.scope,"identity":job.identity,
           "changed":job.changed,"images":images,"cancel_requested":job.stop.is_set()}
    temporary=job.directory/".job.tmp"
    with temporary.open("w",encoding="utf-8") as handle:
        json.dump(value,handle,ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary,job.directory/"job.json")

def ensure_loaded():
    """One queue owner per storage directory, including across server restarts."""
    global loaded_root,queue_lock
    root=storage.root()/".pdf-jobs"
    if loaded_root==root:return root
    if loaded_root is not None:
        raise HTTPException(503,"PDF 存储配置改变，请重启服务")
    root.mkdir(mode=0o700,exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise HTTPException(503,"PDF 任务存储无效")
    import fcntl
    guard=(root/".lock").open("a")
    try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        guard.close()
        raise HTTPException(503,"PDF 队列已被另一服务进程占用")
    queue_lock=guard;loaded_root=root
    pending=[]
    for folder in root.iterdir():
        if not folder.is_dir() or folder.is_symlink() or not re.fullmatch(r"[0-9a-f-]{36}",folder.name):continue
        try:
            meta=json.loads((folder/"job.json").read_text(encoding="utf-8"))
            if meta["id"]!=folder.name:raise ValueError("invalid job ID")
            if meta["state"] not in TERMINAL|{"queued","running"}:raise ValueError("invalid state")
            if meta["state"] in TERMINAL and time.time()-meta["changed"]>TTL:
                shutil.rmtree(folder);continue
            images={}
            if meta["state"] not in TERMINAL:
                for key,(relative,media) in meta["images"].items():
                    path=(folder/relative).resolve()
                    if not path.is_relative_to(folder.resolve()) or not path.is_file() or media not in storage.IMAGE_TYPES:
                        raise ValueError("invalid staged image")
                    images[key]=(str(path),media)
            job=Job(meta["id"],meta["user_id"],meta["scope"],meta["identity"],meta["filename"],folder,images,
                state=meta["state"],stage=meta["stage"],detail=meta.get("detail",""),pages=meta.get("pages",0),
                bytes=meta.get("bytes",0),total_pages=meta.get("total_pages",0),page_ranges=meta.get("page_ranges",""),changed=meta["changed"],
                work_id=meta.get("work_id"),work_version=meta.get("work_version"),work_error=meta.get("work_error",""))
            jobs[job.id]=job
            if job.state not in TERMINAL:
                if meta.get("cancel_requested"):
                    job.stop.set()
                if not job.payload.is_file():
                    change(job,state="failed",stage="恢复失败",detail="排版快照缺失，请重新生成")
                else:
                    job.output.unlink(missing_ok=True)
                    change(job,state="queued",stage="服务重启后等待恢复")
                    pending.append(job)
            elif job.state=="ready" and not job.output.is_file():
                change(job,state="failed",stage="恢复失败",detail="PDF 成品已缺失")
        except Exception:
            logger.warning("Invalid PDF job record: %s",folder.name)
            # Keep corrupt records private for administrator recovery, do not execute.
    for job in sorted(pending,key=lambda item:item.changed):pool.submit(run,job)
    return root

def cleanup():
    # Caller holds lock. Never remove data from a running render.
    root=ensure_loaded()
    stale=[key for key,job in jobs.items() if job.state in TERMINAL and time.time()-job.changed>TTL]
    for key in stale:
        shutil.rmtree(jobs.pop(key).directory,ignore_errors=True)
    return root

async def pdf_maintenance_loop():
    while True:
        try:
            if settings.storage_root:
                def maintain():
                    with lock:cleanup()
                    if settings.database_url:
                        with session_factory()() as db:
                            teaching_works.retire_files(db)
                await asyncio.to_thread(maintain)
        except Exception as exc:
            logger.warning("PDF maintenance unavailable: %s",type(exc).__name__)
        await asyncio.sleep(60)


def change(job, **fields):
    with lock:
        for key, value in fields.items():
            setattr(job, key, value)
        job.changed = time.time()
        persist(job)

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
            # Finish registration before exposing ready; cancellation and registration
            # share the queue lock so a cancelled job cannot publish a work.
            with lock:
                if job.stop.is_set():
                    job.output.unlink(missing_ok=True)
                    change(job, state="cancelled", stage="已取消")
                else:
                    work_id, work_version, work_error = None, None, ""
                    try:
                        payload = json.loads(job.payload.read_text(encoding="utf-8"))
                        with session_factory()() as db:
                            work_id, work_version = teaching_works.register_pdf(
                                db, user_id=job.user_id, scope=job.scope, identity=job.identity,
                                filename=job.filename, path=job.output, payload=payload, pages=result["pages"])
                            db.commit()
                    except Exception as exc:
                        logger.warning("PDF work registration failed: %s", type(exc).__name__)
                        work_id, work_version = None, None
                        work_error = "PDF 已生成，但作品入库失败，请下载成品并重新导出。"
                    change(job, state="ready", stage="生成完成", pages=result["pages"],
                           bytes=result["bytes"], total_pages=result.get("total_pages",result["pages"]),
                           work_id=work_id, work_version=work_version, work_error=work_error)
    except ValueError as exc:
        job.output.unlink(missing_ok=True)
        change(job, state="failed", stage="排版检查失败", detail=str(exc)[:300])
    except Exception as exc:
        logger.error("PDF generation failed: %s", type(exc).__name__)
        job.output.unlink(missing_ok=True)
        change(job, state="failed", stage="生成失败", detail="PDF 渲染环境或文件异常，请重试或联系管理员检查浏览器服务。")
    finally:
        with lock:
            job.payload.unlink(missing_ok=True)
            job.images.clear()
            shutil.rmtree(job.directory/'images',ignore_errors=True)
            if job.id in jobs:persist(job)

def get_job(user, job_id):
    cleanup()
    job = jobs.get(job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "生成记录不存在或已过期")
    return job

def build_snapshot(scope, identity, request, db):
    data = source_export(identity, db) if scope == "source" else export_document(identity, db, chapter=request.chapter_uid)
    if data["export_token"] != request.export_token:
        raise HTTPException(409, "资料在预览后发生变化，请重新打开并检查排版")
    blocks = data["blocks"]
    if request.chapter_uid and scope=="source":
        raise HTTPException(422,"来源资料请使用自由选取内容")
    if request.chapter_uid and data.get("export_chapter_uid")!=request.chapter_uid:
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

def resolve_images(db, data, layout=None):
    ids = {fid for fid in (layout.coverFileId,layout.backCoverFileId) if fid} if layout else set()
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
    images = resolve_images(db, {"blocks":[]} if body.wrap else data, body.layout)
    payload = {"doc": data, "layout": body.layout.model_dump(), "stem": body.stem,
               "answerOnly": body.answerOnly, "source": scope == "source", "page_ranges":body.page_ranges, "preview_pages":body.preview_pages,"wrap":body.wrap.model_dump() if body.wrap else None}
    payload["chapter_uid"] = body.chapter_uid
    payload["selected_uids"] = body.selected_uids
    payload["work_context"] = teaching_works.context(payload)
    if body.wrap:payload["doc"]={**data,"blocks":[]}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    check_complete_export_size(len(raw))
    filename = storage.safe_name(body.filename.strip().removesuffix(".pdf") + ".pdf")
    with lock:
        root=cleanup()
        active = [job for job in jobs.values() if job.state not in TERMINAL]
        if len(active) >= 2:
            raise HTTPException(429, "PDF 生成队列已满，请稍后重试")
        if len(jobs) >= 12:
            raise HTTPException(429, "请先清理已生成的临时 PDF")
        identifier=str(uuid4())
        folder=root/identifier
        folder.mkdir(mode=0o700)
        job=Job(identifier,user.id,scope,identity,filename,folder,{},page_ranges=body.page_ranges)
        try:
            (folder/"images").mkdir(mode=0o700)
            for i,(key,(path,media)) in enumerate(images.items()):
                staged=folder/"images"/str(i)
                # Same private storage filesystem: keep immutable image bytes available
                # even when the original is archived or physically purged after submission.
                os.link(path,staged)
                job.images[key]=(str(staged),media)
            with job.payload.open("wb") as handle:
                handle.write(raw);handle.flush();os.fsync(handle.fileno())
            persist(job)
            jobs[job.id]=job
            pool.submit(run,job)
        except Exception:
            jobs.pop(job.id,None)
            shutil.rmtree(folder,ignore_errors=True)
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
        shutil.rmtree(job.directory)
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
