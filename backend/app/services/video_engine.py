"""Private loopback bridge to the pinned upstream engine. No generic URL proxy."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

SOURCE_REVISION = "fec8a4f8c21b829a8f043a2c3538aff4cc48ea08"
ID = re.compile(r"^[a-f0-9]{32}$")
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def config():
    token = os.environ.get("VIDEO_ENGINE_TOKEN", "")
    port = os.environ.get("VIDEO_ENGINE_PORT", "8766")
    if not token or not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise HTTPException(503, "独立视频引擎尚未配置")
    return f"http://127.0.0.1:{int(port)}/api/v1", token

def engine_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise HTTPException(502, "视频引擎返回无效编号")
    return value

def open_response(method, path, body=None, range_header=None):
    base, token = config()
    headers = {"X-API-Key": token, "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode()
    if range_header:
        if not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", range_header):
            raise HTTPException(416, "仅支持单段视频范围")
        headers["Range"] = range_header
    try:
        return build_opener(ProxyHandler({}), NoRedirect()).open(
            Request(base + path, data=data, method=method, headers=headers), timeout=15)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if status in (400, 404, 409, 416, 422, 429):
            raise HTTPException(status, f"视频引擎拒绝请求（{status}），请检查题源、模型配置或任务状态") from None
        raise HTTPException(502, f"视频引擎接口异常（{status}）") from None
    except (URLError, OSError, TimeoutError):
        raise HTTPException(503, "视频引擎暂不可达；提交结果不确定时请先核对引擎任务，勿重复生成") from None

def call(method, path, body=None):
    with open_response(method, path, body) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(502, "引擎响应过大")
    try:
        return json.loads(raw)
    except (UnicodeError, ValueError):
        raise HTTPException(502, "引擎响应格式错误") from None

def media(ident, download=False, range_header=None):
    suffix = "download" if download else "stream"
    response = open_response("GET", f"/videos/{engine_id(ident)}/{suffix}", range_header=range_header)
    if response.headers.get_content_type() != "video/mp4":
        response.close()
        raise HTTPException(502, "视频响应类型不正确")
    headers = {k: response.headers[k] for k in ("Content-Length", "Content-Range", "Accept-Ranges") if k in response.headers}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{ident}.mp4"'
    def chunks():
        try:
            while True:
                data = response.read(256 * 1024)
                if not data:
                    break
                yield data
        finally:
            response.close()
    return StreamingResponse(chunks(), status_code=response.status, media_type="video/mp4", headers=headers)


def configure_production_model(model,effort='default'):
    """The pinned upstream has separate groups; set them together, not just the UI."""
    groups=call("GET","/ai/groups").get("groups",{})
    def matches(group):
        return group.get("configured") and group.get("mode")=="qoder_cli" and group.get("model_id")==model and group.get("reasoning_effort","default")==effort
    if all(matches(groups.get(key,{})) for key in ("other","edit")):
        return
    result=call("PUT","/ai/global",{"mode":"qoder_cli","model_id":model,"reasoning_effort":effort,"speed":"default","timeout_seconds":900})
    if not result.get("configured") or result.get("model_id")!=model:
        raise HTTPException(502,"视频引擎未确认模型配置")
    groups=call("GET","/ai/groups").get("groups",{})
    if not all(matches(groups.get(key,{})) for key in ("other","edit")):
        raise HTTPException(502,"视频制作与微调模型尚未同步")
