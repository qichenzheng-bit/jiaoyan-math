"""Bounded extraction of text-layer PDFs; not OCR or a mathematical verifier."""
import shutil
import subprocess
import tempfile
from fastapi import HTTPException
from app.services import storage

def extract_pdf(file,start,end):
    if file.archived or file.media_type!="application/pdf":
        raise HTTPException(415,"请选择未归档的PDF文件")
    if not 1<=start<=end<=10000 or end-start>=10:
        raise HTTPException(422,"每批最多10个连续物理页")
    exe=shutil.which("pdftotext")
    limiter=shutil.which("prlimit")
    if not exe or not limiter:
        raise HTTPException(503,"服务器缺少 poppler-utils 或 prlimit，请先安装或粘贴原文")
    try:
        with tempfile.TemporaryFile() as out:
            result=subprocess.run([limiter,"--as=536870912","--fsize=262144","--cpu=15","--",exe,"-f",str(start),"-l",str(end),"-layout","-enc","UTF-8",str(storage.file_path(file)),"-"],stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.DEVNULL,timeout=20,check=False)
            if result.returncode:
                raise HTTPException(422,"PDF提取失败，请确认页码、密码保护和文件有效性")
            out.seek(0)
            raw=out.read(262145)
            if len(raw)>262144:
                raise HTTPException(422,"提取文本过大，请缩小页码范围")
            text=raw.decode("utf-8").strip()
    except (OSError,UnicodeError,subprocess.TimeoutExpired):
        raise HTTPException(422,"PDF文本提取失败或超时")
    if not text:
        raise HTTPException(422,"没有可提取文字；扫描件需要视觉识别")
    if len(text)>24000:
        raise HTTPException(422,"每批最多24000字，请缩小页码范围")
    return text
