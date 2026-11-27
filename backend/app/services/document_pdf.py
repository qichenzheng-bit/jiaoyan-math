"""Generate a searchable PDF from an isolated, compiled math-layout renderer."""
import json
import mimetypes
import os
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

PDF_MAX_BYTES = 200_000_000
RENDER_ORIGIN = "http://wg-pdf.invalid"

def selected_pages(spec: str, total: int) -> list[int]:
    """Return unique zero-based physical page indices in document order."""
    import re
    if not spec.strip():
        return list(range(total))
    if len(spec)>2000 or not re.fullmatch(r"[0-9,，、\s-]+", spec):
        raise ValueError("页码范围格式无效，例如 1-3,5")
    result=set()
    for part in re.split(r"[,，、]",spec):
        match=re.fullmatch(r"\s*(\d{1,5})(?:\s*-\s*(\d{1,5}))?\s*",part)
        if not match:
            raise ValueError("页码范围格式无效，例如 1-3,5")
        first=int(match[1]);last=int(match[2] or first)
        if not 1<=first<=last<=total:
            raise ValueError(f"页码超出范围，当前共 {total} 页")
        result.update(range(first-1,last))
    return sorted(result)

def launch_options():
    # Deployment may select an administrator-installed Chromium. Never accept a
    # browser executable or external URL from an API request.
    executable = os.environ.get("WG_PDF_CHROME") or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    result = {"headless": True, "chromium_sandbox": os.environ.get("WG_PDF_CHROMIUM_SANDBOX", "1") != "0",
              "args": ["--disable-dev-shm-usage"]}
    if executable:
        result["executable_path"] = executable
    return result

def render_pdf(payload_path: Path, images: dict, output: Path, stage, cancelled, dist: Path | None = None):
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader, PdfWriter
    dist = (dist or (Path(__file__).resolve().parents[3] / "frontend" / "dist")).resolve()
    index = dist / "index.html"
    assets = (dist / "assets").resolve()
    if not index.is_file() or not assets.is_dir():
        raise RuntimeError("前端排版程序尚未构建")
    if cancelled():
        return None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_options())
        try:
            context = browser.new_context(service_workers="block", viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            def route_request(route):
                url = urlsplit(route.request.url)
                path = unquote(url.path)
                if url.scheme != "http" or url.netloc != "wg-pdf.invalid" or route.request.method != "GET":
                    route.abort()
                    return
                if path == "/__layout_pdf":
                    route.fulfill(path=str(index), content_type="text/html")
                elif path == "/api/layout-payload":
                    route.fulfill(path=str(payload_path), content_type="application/json")
                elif path.startswith("/assets/"):
                    local = (dist / path.lstrip("/")).resolve()
                    if not local.is_relative_to(assets) or not local.is_file():
                        route.fulfill(status=404, body="")
                    else:
                        route.fulfill(path=str(local), content_type=mimetypes.guess_type(local.name)[0] or "application/octet-stream")
                elif path in images:
                    local, media = images[path]
                    if not Path(local).is_file():
                        route.fulfill(status=404, body="")
                    else:
                        route.fulfill(path=str(local), content_type=media)
                else:
                    route.fulfill(status=404, body="")
            context.route("**/*", route_request)
            stage("分页与公式渲染")
            page.goto(RENDER_ORIGIN + "/__layout_pdf", wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_selector('[data-pdf-state="ready"],[data-pdf-state="failed"]', timeout=120_000)
            state = page.locator("[data-pdf-state]").first
            if state.get_attribute("data-pdf-state") != "ready":
                alert = page.get_by_role("alert").first
                detail = alert.inner_text(timeout=3000) if alert.count() else "排版检查失败"
                raise ValueError(detail[:300])
            pages = int(state.get_attribute("data-pdf-pages") or 0)
            if pages < 1:
                raise ValueError("未生成可导出的页面")
            if cancelled():
                return None
            request=json.loads(payload_path.read_text(encoding="utf-8"))
            if request.get("page_ranges","").strip() and request.get("preview_pages")!=pages:
                raise ValueError("服务器页数与预览不同，请重新检查后选择页码")
            indices=selected_pages(request.get("page_ranges",""),pages)
            stage("生成 PDF")
            page.pdf(path=str(output), prefer_css_page_size=True, print_background=True,
                     display_header_footer=False, tagged=True, outline=True)
            if cancelled():
                return None
            stage("核对 PDF 页数及文件完整性")
            if not output.is_file() or output.stat().st_size > PDF_MAX_BYTES:
                raise ValueError("PDF 文件超过 200 MB，请按章节导出")
            with output.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise ValueError("生成文件不是有效 PDF")
                stream.seek(0)
                reader = PdfReader(stream)
                if len(reader.pages) != pages:
                    raise ValueError("PDF 页数与分页预览不一致，已阻止下载")
            if len(indices)!=pages:
                stage("提取指定物理页码")
                subset=output.with_suffix(".selected.pdf")
                try:
                    with output.open("rb") as stream:
                        writer=PdfWriter()
                        writer.append(PdfReader(stream),pages=indices,import_outline=True)
                        with subset.open("wb") as handle:
                            writer.write(handle)
                        writer.close()
                    if len(PdfReader(subset).pages)!=len(indices):
                        raise ValueError("指定页码提取失败")
                    subset.replace(output)
                finally:
                    subset.unlink(missing_ok=True)
            return {"pages": len(indices), "bytes": output.stat().st_size, "total_pages":pages}
        finally:
            browser.close()
