"""Bounded raster preview of existing PDFs, never rebuild the document."""
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from fastapi import HTTPException

slots = threading.BoundedSemaphore(2)


def render_page(path: Path, page: int, dpi: int = 120) -> bytes:
    exe, limiter = shutil.which("pdftoppm"), shutil.which("prlimit")
    if not exe or not limiter:
        raise HTTPException(503, "服务器未安装 PDF 逐页预览工具，请打开原 PDF")
    if not 1 <= page <= 10000 or not 72 <= dpi <= 180:
        raise HTTPException(422, "预览参数无效")
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "预览正在处理，请重试")
    try:
        with tempfile.TemporaryDirectory(prefix="wg-preview-") as folder:
            target = Path(folder) / "page"
            result = subprocess.run(
                [limiter,"--as=805306368","--cpu=12","--fsize=16777216","--",
                 exe,"-f",str(page),"-l",str(page),"-singlefile","-r",str(dpi),
                 "-scale-to",str(min(3000,round(dpi*16))),"-png",str(path),str(target)],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                timeout=18,check=False)
            output = target.with_suffix(".png")
            if result.returncode or not output.is_file() or output.stat().st_size > 16777216:
                raise HTTPException(422, "该页无法预览，请打开原 PDF")
            data = output.read_bytes()
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise HTTPException(422, "页面预览无效")
            return data
    except (OSError, subprocess.TimeoutExpired):
        raise HTTPException(503, "页面预览失败或超时，请重试")
    finally:
        slots.release()
