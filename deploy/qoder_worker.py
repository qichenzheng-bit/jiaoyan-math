#!/usr/bin/env python3
"""Unix-socket-only Qoder CN worker. Separate non-root service account."""
import errno
import base64
import binascii
import json
import math
import os
import re
import selectors
import shutil
import signal
import socketserver
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

SOCKET = "/run/jiaoyan-qoder/worker.sock"
VISION_MAX_BYTES = 8 * 1024 * 1024
VISION_TYPES = {"image/png":".png","image/jpeg":".jpg","image/webp":".webp","image/gif":".gif"}

def vision_attachment(data):
    """Accept bounded image bytes only; never trust caller-provided paths or filenames."""
    if not isinstance(data,dict) or set(data)!={"media_type","base64"}: raise ValueError("image attachment required")
    media,encoded=data["media_type"],data["base64"]
    if not isinstance(media,str) or media not in VISION_TYPES or not isinstance(encoded,str) or len(encoded)>4*((VISION_MAX_BYTES+2)//3): raise ValueError("invalid attachment")
    try: raw=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error): raise ValueError("invalid image encoding")
    valid=(media=="image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n") or media=="image/jpeg" and raw.startswith(b"\xff\xd8\xff") or media=="image/webp" and raw[:4]==b"RIFF" and raw[8:12]==b"WEBP" or media=="image/gif" and raw[:6] in (b"GIF87a",b"GIF89a"))
    if not valid or not 0<len(raw)<=VISION_MAX_BYTES: raise ValueError("invalid image or size")
    return VISION_TYPES[media],raw

AUTH_DOMAINS = ("qoder.cn", "qoder.com.cn", "qoder.com", "aliyun.com", "alibabacloud.com")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
URL = re.compile(r"https://[^\s<>\x00-\x20\"']+")

def executable():
    found = shutil.which("qoderclicn") or shutil.which("qodercn")
    if found:
        return found
    home = Path.home()
    for path in (home / ".qoder-cn/bin/qoderclicn/qoderclicn", home / ".qoder-cn/bin/qoderclicn", home / ".local/bin/qoderclicn", home / ".local/bin/qodercn", home / ".qoder-cn/bin/qodercn"):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None

def authorization_url(text):
    for match in URL.finditer(ANSI.sub("", text)):
        value = match.group().rstrip(").,;]}")
        try:
            parts = urlsplit(value)
            host = (parts.hostname or "").lower()
            if (parts.scheme == "https" and not parts.username and not parts.password and
                parts.port in (None, 443) and
                any(host == d or host.endswith("." + d) for d in AUTH_DOMAINS) and
                len(value) <= 8192):
                # Exclude bare documentation/homepage links. Never expose raw CLI logs.
                if parts.query or any(x in parts.path.lower() for x in ("auth", "login", "sign", "oauth", "device")):
                    return value
        except ValueError:
            continue
    return ""

lock = threading.Lock()
login = {"state": "idle", "url": "", "detail": "尚未发起网页授权"}
login_process = None
verified_at = None

# Model discovery follows the legacy CLI table parser, with strict identifiers.
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}")
FALLBACK_MODELS = ("Auto", "Fast")
catalog = None
catalog_at = None
catalog_efforts = {}
catalog_capability_source = "unavailable"
AUTH_STATE_PATH = Path.home() / ".jiaoyan-auth-state.json"
retained_auth = False
user_disconnected = False
SDK_PYTHON = Path("/opt/jiaoyan-qoder/sdk-venv/bin/python")
usage_cache = None
USAGE_CACHE_SECONDS = 60
SUPPORTED_EFFORTS = ('none','off','disabled','low','medium','high','xhigh','max')

def parse_models(output):
    names = []
    in_list = False
    for raw in ANSI.sub("", output).splitlines():
        text = raw.strip()
        if not text:
            continue
        if not in_list:
            if re.fullmatch(r"(?:available\s+)?models?(?:\s*\([^)]*\))?:?", text, re.I):
                in_list = True
                continue
            if text.startswith(("- ", "* ")):
                in_list = True
            else:
                continue
        if text.startswith("--"):
            continue
        name = text[2:].strip() if text.startswith(("- ", "* ")) else text
        if MODEL_ID.fullmatch(name) and name.lower() not in {"model","models","warning","available","error","usage","id","name","description","none"}:
            if name not in names:
                names.append(name)
    return names[:200]

def parse_catalog(output):
    """Only explicit per-model capabilities are evidence. Never infer from a model name."""
    clean = ANSI.sub("", output)
    try:
        payload = json.loads(clean)
    except ValueError:
        payload = None
    rows = payload.get("models") if isinstance(payload, dict) else payload
    result = {}
    if isinstance(rows, list):
        for row in rows:
            ident = row if isinstance(row, str) else row.get("id", row.get("model_id", row.get("value", ""))) if isinstance(row,dict) else ""
            if not isinstance(ident,str) or not MODEL_ID.fullmatch(ident):
                continue
            if isinstance(row,dict) and row.get("isEnabled") is False:continue
            values = row.get("efforts", row.get("reasoning_efforts", [])) if isinstance(row,dict) else []
            explicit = set(v for v in values if isinstance(v,str)) if isinstance(values,(list,dict)) else set()
            # Official ModelInfo uses thinking_config.enabled.efforts (a keyed map).
            for record in (row, row.get("serverModel",{})) if isinstance(row,dict) else ():
                config=record.get("thinking_config") if isinstance(record,dict) else None
                if not isinstance(config,dict):continue
                enabled=config.get("enabled")
                if isinstance(enabled,dict) and isinstance(enabled.get("efforts"),dict):
                    explicit.update(enabled["efforts"])
                if isinstance(config.get("disabled"),dict):explicit.add("disabled")
            result[ident] = [e for e in SUPPORTED_EFFORTS if e in explicit]
    else:
        result = {name: [] for name in parse_models(clean)}
        for line in clean.splitlines():
            match = re.fullmatch(r"\s*(?:[-*]\s+)?([A-Za-z0-9][A-Za-z0-9._:/-]{0,79})\s+(?:reasoning[ _-]*efforts?|efforts?)\s*[:=]\s*\[?([a-zA-Z, /|]+)\]?\s*",line,re.I)
            if match:
                ident, values = match.groups()
                result[ident]=[e for e in SUPPORTED_EFFORTS if e in re.split(r"[, /|]+",values.lower())]
    return dict(list(result.items())[:200])

def parse_sdk_catalog(payload):
    # SDK value is the internal identifier; CLI expects display names for built-in
    # models. Keep existing UI/DB identifiers and never map by list position.
    rows=[]
    seen=set()
    for row in payload.get("models",[]):
        if not isinstance(row,dict) or row.get("isEnabled") is False:continue
        value=row.get("value")
        name=row.get("displayName")
        if not isinstance(value,str) or not MODEL_ID.fullmatch(value):continue
        if value in ("auto","fast"):name=value.capitalize()
        if not isinstance(name,str) or not MODEL_ID.fullmatch(name):continue
        if name in seen:continue
        seen.add(name)
        rows.append({**row,"id":name})
    return parse_catalog(json.dumps({"models":rows}))

SDK_CATALOG_SCRIPT = r"""
import asyncio, json, sys
from qodercn_agent_sdk import QoderAgentOptions, QoderSDKClient, qodercli_auth

async def main():
    options = QoderAgentOptions(auth=qodercli_auth(), tools=[],
        allowed_tools=[], cwd=sys.argv[2])
    async with QoderSDKClient(options=options) as client:
        models = await client.get_available_models()
        print(json.dumps({"models": models}, ensure_ascii=False))

asyncio.run(main())
"""

def sdk_catalog(exe):
    if not SDK_PYTHON.is_file():return None,"sdk_missing"
    try:
        with tempfile.TemporaryDirectory(prefix="qoder-sdk-models-") as work:
            proc=subprocess.Popen([str(SDK_PYTHON),"-c",SDK_CATALOG_SCRIPT,exe,work],
                cwd=work,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,
                env={**os.environ,"PATH":str(Path(exe).parent)+os.pathsep+os.environ.get("PATH","")})
            try:
                out,_=proc.communicate(timeout=25)
            except subprocess.TimeoutExpired:
                stop_process(proc);proc.communicate()
                return None,"sdk_timeout"
        if proc.returncode!=0:return None,"sdk_failed"
        payload=json.loads(out.decode("utf-8"))
        if not isinstance(payload,dict) or not isinstance(payload.get("models"),list):return None,"sdk_invalid"
        metadata=parse_sdk_catalog(payload)
        if not metadata:return None,"sdk_empty"
        return metadata,"sdk"
    except (OSError,ValueError):
        return None,"sdk_failed"

SDK_USAGE_SCRIPT = SDK_CATALOG_SCRIPT.replace(
    'models = await client.get_available_models()','usage = await client.get_usage_info()'
).replace('{"models": models}','{"usage": usage}')

def parse_usage(payload):
    """Whitelist account quota fields; never expose account identifiers or raw SDK responses."""
    if not isinstance(payload,dict):return None
    def number(v):
        if type(v) in (int,float) and math.isfinite(v) and v>=0:return v
        return None
    packs=[]
    for key,label in (("userQuota","套餐额度"),("addOnQuota","资源包"),("orgResourcePackage","组织共享额度")):
        row=payload.get(key)
        if not isinstance(row,dict):continue
        fields={name:number(row.get("cap" if name=="total" and key=="orgResourcePackage" else name)) for name in ("total","used","remaining")}
        if all(v is None for v in fields.values()):continue
        unit=row.get("unit")
        unit=unit if isinstance(unit,str) and unit.lower() in ("credits","credit") else None
        packs.append({"kind":key,"label":label,**fields,"unit":unit,"available":row.get("available") if type(row.get("available")) is bool else None})
    if not packs:return None
    return {"packs":packs,"quota_exceeded":payload.get("isQuotaExceeded") if type(payload.get("isQuotaExceeded")) is bool else None,
            "usage_percentage":number(payload.get("totalUsagePercentage"))}

def sdk_usage(exe):
    if not SDK_PYTHON.is_file():return None,"sdk_missing"
    try:
        with tempfile.TemporaryDirectory(prefix="qoder-sdk-usage-") as work:
            proc=subprocess.Popen([str(SDK_PYTHON),"-c",SDK_USAGE_SCRIPT,exe,work],cwd=work,
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,
                env={**os.environ,"PATH":str(Path(exe).parent)+os.pathsep+os.environ.get("PATH","")})
            try:out,_=proc.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                stop_process(proc);proc.communicate();return None,"sdk_timeout"
        if proc.returncode!=0:return None,"sdk_failed"
        payload=json.loads(out.decode("utf-8"))
        data=parse_usage(payload.get("usage")) if isinstance(payload,dict) else None
        return (data,"sdk") if data else (None,"sdk_unavailable")
    except (OSError,ValueError):return None,"sdk_failed"

def usage_status(refresh=False):
    global usage_cache
    with lock:
        if user_disconnected:return 200,{"available":False,"reason":"已主动退出 AI"}
        if login_process is not None:return 200,{"available":False,"reason":"正在授权"}
        cached=usage_cache
        fresh=cached and time.time()-cached["updated_at"]<USAGE_CACHE_SECONDS
        if not refresh or fresh or chat_active:
            if cached:return 200,{**cached,"stale":not fresh,"busy":bool(chat_active)}
            if not refresh or chat_active:return 200,{"available":False,"reason":"暂无额度快照，请刷新或等待当前任务完成"}
    exe=executable()
    data,reason=sdk_usage(exe) if exe else (None,"cli_missing")
    with lock:
        if data:
            usage_cache={"available":True,"source":"sdk","updated_at":int(time.time()),**data}
            return 200,{**usage_cache,"stale":False}
        if usage_cache:return 200,{**usage_cache,"stale":True,"reason":reason}
        return 200,{"available":False,"reason":reason}

def save_auth_state():
    """Only non-secret metadata. Credentials remain exclusively in the official CLI home."""
    fd,name=tempfile.mkstemp(dir=AUTH_STATE_PATH.parent,prefix=".jiaoyan-auth-")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as handle:
            json.dump({"retained":retained_auth,"disconnected":user_disconnected,
                       "verified_at":verified_at,"catalog":catalog_efforts if catalog is not None else None,
                       "catalog_at":catalog_at,"capability_source":catalog_capability_source},handle)
            handle.flush();os.fsync(handle.fileno())
        os.replace(name,AUTH_STATE_PATH)
    finally:
        Path(name).unlink(missing_ok=True)

def persist_auth_metadata():
    try:save_auth_state()
    except OSError:pass

def restore_auth_state():
    global retained_auth,user_disconnected,verified_at,catalog,catalog_at,catalog_efforts,catalog_capability_source
    try:
        if AUTH_STATE_PATH.stat().st_size>524288:return
        data=json.loads(AUTH_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data,dict):return
    except (OSError,ValueError):return
    user_disconnected=data.get("disconnected") is True
    retained_auth=data.get("retained") is True and not user_disconnected
    if user_disconnected:
        login.update(state="disconnected",url="",detail="已主动退出本系统 AI")
        return
    if retained_auth:
        last=data.get("verified_at")
        verified_at=last if type(last) is int and last>0 else None
        login.update(state="finished",url="",detail="已保留上次授权，继续使用官方 CLI 凭据")
    old=data.get("catalog")
    updated=data.get("catalog_at")
    if isinstance(old,dict) and type(updated) is int and 0<=time.time()-updated<86400:
        catalog_efforts={k:[e for e in SUPPORTED_EFFORTS if e in v] for k,v in list(old.items())[:200] if isinstance(k,str) and MODEL_ID.fullmatch(k) and isinstance(v,list)}
        catalog=list(catalog_efforts);catalog_at=updated
        catalog_capability_source=data.get("capability_source") if data.get("capability_source") in ("sdk","cli_metadata") else "unavailable"

def disconnect():
    global usage_cache
    global retained_auth,user_disconnected,verified_at,catalog,catalog_at,catalog_efforts,catalog_capability_source
    with lock:
        if chat_active or login_process is not None:return 409,{"detail":"请先完成当前任务或取消授权"}
        old=(retained_auth,user_disconnected,verified_at,catalog,catalog_at,catalog_efforts,catalog_capability_source)
        retained_auth=False;user_disconnected=True;verified_at=None
        catalog,catalog_at,catalog_efforts=None,None,{}
        catalog_capability_source="unavailable"
        try:save_auth_state()
        except OSError:
            retained_auth,user_disconnected,verified_at,catalog,catalog_at,catalog_efforts,catalog_capability_source=old
            return 503,{"detail":"无法保存退出状态，未断开"}
        usage_cache=None
        login.update(state="disconnected",url="",detail="已退出本系统 AI；官方 CLI 凭据未删除")
        return 200,dict(login)

def model_catalog():
    with lock:
        names = list(FALLBACK_MODELS if catalog is None else catalog)
        return {"models": [{"id": n, "label": n, "efforts": list(catalog_efforts.get(n, [])) if catalog is not None else []} for n in names],
                "source": "fallback" if catalog is None else "cli",
                "updated_at": catalog_at,"capability_source":catalog_capability_source}

def refresh_models():
    global catalog, catalog_at, catalog_efforts, catalog_capability_source, retained_auth
    with lock:
        if user_disconnected:return 409,{"detail":"已退出本系统 AI，请主动登录"}
        if login_process is not None or chat_active:
            return 409, {"detail": "请先完成当前授权或对话"}
    exe = executable()
    if not exe:
        return 503, {"detail": "未安装 Qoder CN CLI"}
    try:
        metadata,capability_source=sdk_catalog(exe)
        if metadata is not None:
            with lock:
                catalog, catalog_at, catalog_efforts = list(metadata),int(time.time()),metadata
                catalog_capability_source=capability_source
                retained_auth=True
                if login["state"] not in ("starting","waiting"):login.update(state="finished",url="",detail="官方 SDK 模型清单已获取，已保留授权")
                persist_auth_metadata()
            return 200,model_catalog()
        with tempfile.TemporaryDirectory(prefix="qoder-models-") as work:
            proc = subprocess.Popen([exe, "--list-models"], cwd=work, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                out, err = proc.communicate(timeout=35 if capability_source=="sdk_missing" else 15)
            except subprocess.TimeoutExpired:
                stop_process(proc)
                proc.communicate()
                return 504, {"detail": "模型清单读取超时，保留此前清单"}
        output = out.decode("utf-8", "replace")
        no_models = "no models available" in (output + err.decode("utf-8", "replace")).lower()
        if proc.returncode != 0 and not no_models:
            return 503, {"detail": "CLI 模型探测失败，保留此前清单"}
        metadata = {} if no_models else parse_catalog(output)
        names = list(metadata)
        if not names and not no_models:
            return 503, {"detail": "无法解析 CLI 模型清单，保留此前清单"}
        with lock:
            catalog, catalog_at, catalog_efforts = names, int(time.time()), metadata
            catalog_capability_source="cli_metadata" if any(metadata.values()) else capability_source
            persist_auth_metadata()
        return 200, model_catalog()
    except OSError:
        return 503, {"detail": "无法启动模型探测"}

def allowed_model(model):
    if not isinstance(model, str) or not MODEL_ID.fullmatch(model):
        return False
    with lock:
        return model in (FALLBACK_MODELS if catalog is None else catalog)

def stop_process(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

def login_worker(proc):
    global login_process, retained_auth,user_disconnected,verified_at,catalog,catalog_at,catalog_efforts,catalog_capability_source
    deadline = time.monotonic() + 300
    link_deadline = time.monotonic() + 45
    buffer = ""
    outcome = "failed"
    detail = "CLI 授权未完成；可重新发起或在服务器终端检查"
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                events = sel.select(0.25)
                for key, _ in events:
                    data = os.read(key.fd, 4096)
                    if data:
                        buffer = (buffer + data.decode("utf-8", "replace"))[-32768:]
                        link = authorization_url(buffer)
                        if link:
                            with lock:
                                if login_process is proc and login["state"] == "starting":
                                    login.update(state="waiting", url=link, detail="请在浏览器完成官方授权，然后验证模型")
                    else:
                        sel.unregister(key.fileobj)
                if proc.poll() is not None:
                    if proc.returncode == 0:
                        outcome, detail = "finished", "CLI 登录流程已结束，请验证模型确认授权有效"
                    break
                if time.monotonic() >= link_deadline and not authorization_url(buffer):
                    outcome, detail = "failed", "CLI 未返回可识别的官方授权链接；请检查 CLI 版本及服务器网络后重试"
                    break
            else:
                outcome, detail = "expired", "授权已超时，请重新发起"
    except OSError:
        pass
    finally:
        if proc.poll() is None:
            stop_process(proc)
        proc.wait()
        if proc.stdout:
            proc.stdout.close()
        with lock:
            if login_process is proc:
                if login["state"] != "cancelled":
                    login.update(state=outcome, url="", detail=detail)
                    if outcome=="finished":
                        retained_auth=True;user_disconnected=False;verified_at=None
                        catalog,catalog_at,catalog_efforts=None,None,{}
                        catalog_capability_source="unavailable"
                        persist_auth_metadata()
                login_process = None

def start_login():
    global usage_cache
    global login_process, verified_at, catalog, catalog_at, catalog_efforts, catalog_capability_source
    with lock:
        if chat_active:
            return 409, {"detail": "请先完成当前对话"}
        if login_process is not None:
            return 200, dict(login)
        exe = executable()
        if not exe:
            return 503, {"detail": "未安装 Qoder CN CLI"}
        env = dict(os.environ, CI="true", BROWSER="www-browser", NO_COLOR="1")
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "MIR_SOCKET"):
            env.pop(name, None)
        try:
            proc = subprocess.Popen([exe, "login"], cwd=str(Path.home()), env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except OSError:
            return 503, {"detail": "无法启动官方登录命令"}
        login_process = proc
        usage_cache=None
        login.update(state="starting", url="", detail="正在获取官方授权链接")
        threading.Thread(target=login_worker, args=(proc,), daemon=True).start()
        return 200, dict(login)

def cancel_login():
    with lock:
        if login_process is not None:
            login.update(state="cancelled", url="", detail="已取消本次授权")
            stop_process(login_process)
        return dict(login)

def status():
    with lock:
        available = bool(executable())
        return {"available": available, "detail": "CLI 已安装" if available else "未检测到 qoderclicn",
                "verified_at": verified_at, "login": dict(login), "auth_ui": True, "model_discovery": True, "worker_version": 15, "native_agent": SDK_PYTHON.is_file(), "vision_attachment": True, "usage_discovery":True, "retained_auth":retained_auth,"user_disconnected":user_disconnected, "video_inference": True, "busy": bool(chat_active or login_process is not None), "chat_available": available and not user_disconnected, "durable_results": True}

def invoke(model, prompt):
    global verified_at,retained_auth
    with lock:
        if user_disconnected:return 409,{"detail":"已退出本系统 AI，请主动登录"}
        if login_process is not None or chat_active:
            return 409, {"detail": "请先完成当前授权或对话"}
    exe = executable()
    if not exe:
        return 503, {"detail": "未安装 Qoder CN CLI"}
    with tempfile.TemporaryDirectory(prefix="qoder-test-") as work:
        try:
            proc = subprocess.Popen([exe, "-m", model, "--tools", "", "--no-session-persistence", "-p",
                    "请直接回答以下数学或教研问题，不调用工具：\n" + prompt],
                    cwd=work, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, start_new_session=True)
            try:
                out, err = proc.communicate(timeout=40)
            except subprocess.TimeoutExpired:
                stop_process(proc)
                proc.communicate()
                return 504, {"detail": "模型调用超时，请检查账号授权及网络"}
            if proc.returncode != 0:
                return 503, {"detail": "CLI 调用失败，请检查登录状态及网络"}
            answer = out.decode("utf-8", errors="replace").strip()
            if not answer:
                return 503, {"detail": "CLI 未返回正文"}
            with lock:
                verified_at = int(time.time());retained_auth=True;persist_auth_metadata()
            return 200, {"model": model, "answer": answer[:30000]}
        except OSError:
            return 503, {"detail": "CLI 无法启动"}


# Chat jobs are intentionally separate from the CLI's own session persistence.
# All state is bounded, and no tools or raw event logs are exposed.
chat_jobs = {}
chat_active = None
JOB_ID = re.compile(r"[0-9a-f-]{36}")

def chat_event(event):
    if not isinstance(event, dict):
        return "", "", False
    kind = event.get("type")
    if kind == "error" or event.get("is_error"):
        return "", "", True
    inner = event.get("event")
    if isinstance(inner, dict) and inner.get("type") == "content_block_delta":
        delta = inner.get("delta")
        if isinstance(delta, dict) and delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
            return delta["text"], "", False
    if kind == "assistant":
        message = event.get("message")
        if isinstance(message, dict):
            blocks = message.get("content")
            if isinstance(blocks, list):
                return "", "".join(b["text"] for b in blocks if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)), False
            if isinstance(blocks, str):
                return "", blocks, False
    if kind == "result":
        value = event.get("result")
        return "", value if isinstance(value, str) else "", False
    return "", "", False

def chat_snapshot(job,live=False):
    result={k:job[k] for k in ("id","state","answer","detail")}
    if job.get("native_session"):result["native_session"]=job["native_session"]
    if live and job.get("pending"):result["pending_tool"]=job["pending"]
    return result


# Finished snapshots survive a worker restart until the web service reads them.
# A bounded, private cache is not a replacement for the PostgreSQL history.
SNAPSHOT_DIR = Path.home() / ".jiaoyan-job-results"
SNAPSHOT_MAX = 512
SNAPSHOT_TTL = 7 * 86400

def save_snapshot(job):
    if not JOB_ID.fullmatch(job["id"]):
        return
    SNAPSHOT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / (job["id"] + ".json")
    fd, name = tempfile.mkstemp(dir=SNAPSHOT_DIR, prefix=".result-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({**chat_snapshot(job), "saved_at": int(time.time())}, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def load_snapshot(ident):
    if not JOB_ID.fullmatch(ident):
        return None
    try:
        path = SNAPSHOT_DIR / (ident + ".json")
        if path.stat().st_size > 2_000_000:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("id") != ident or time.time()-value.get("saved_at",0)>SNAPSHOT_TTL:
            return None
        if value.get("state") == "running":
            value.update(state="failed",detail="执行服务已重启；保留已写入的结果")
        return chat_snapshot(value)
    except (OSError,ValueError,TypeError,KeyError):
        return None

def prune_snapshots():
    try:
        files = sorted(SNAPSHOT_DIR.glob("*.json"), key=lambda p:p.stat().st_mtime, reverse=True)
        for i,path in enumerate(files):
            if i>=SNAPSHOT_MAX or time.time()-path.stat().st_mtime>SNAPSHOT_TTL:
                path.unlink(missing_ok=True)
    except OSError:
        pass

def chat_run(job, exe, model, prompt, attachment=None):
    video = job.get("video", False)
    output_limit = 300000 if video else 48000
    global chat_active,verified_at,retained_auth
    proc = None
    failure = False
    try:
        with tempfile.TemporaryDirectory(prefix="qoder-chat-") as cwd:
            # Prompt is passed as one argv entry; bounded by API and worker.
            args = [exe,"-m",model,"--tools","","--no-session-persistence","--output-format","stream-json"]
            if video:
                if job["system"]: args += ["--system-prompt", job["system"]]
            if job["effort"] != "default": args += ["--reasoning-effort",job["effort"]]
            if attachment is not None:
                suffix,raw=attachment
                image=Path(cwd)/("source"+suffix)
                image.write_bytes(raw)
                args += ["--attachment",str(image)]
            proc = subprocess.Popen(args+["-p",prompt],cwd=cwd,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            with lock:
                job["proc"] = proc
                if job["cancel"]: stop_process(proc)
            deadline = time.monotonic()+(job["timeout"] if video else 240)
            buffer = b""
            with selectors.DefaultSelector() as sel:
                sel.register(proc.stdout,selectors.EVENT_READ)
                while time.monotonic()<deadline:
                    with lock:
                        if job["cancel"]: break
                    if not sel.select(.25):
                        if proc.poll() is not None: break
                        continue
                    chunk=os.read(proc.stdout.fileno(),8192)
                    if not chunk: break
                    buffer+=chunk
                    if len(buffer)>2_000_000:
                        failure=True
                        break
                    while b"\n" in buffer:
                        raw,buffer=buffer.split(b"\n",1)
                        try: event=json.loads(raw)
                        except (ValueError,UnicodeError): continue
                        delta,final,bad=chat_event(event)
                        failure=failure or bad
                        with lock:
                            candidate = final or (job["answer"]+delta)
                            if video and len(candidate)>output_limit: failure=True
                            else: job["answer"]=candidate[:output_limit]
                        if failure: break
                    if failure: break
                else:
                    failure=True
            if buffer.strip():
                try:
                    delta,final,bad=chat_event(json.loads(buffer))
                    failure=failure or bad
                    with lock:
                        candidate = final or (job["answer"]+delta)
                        if video and len(candidate)>output_limit: failure=True
                        else: job["answer"]=candidate[:output_limit]
                except (ValueError,UnicodeError): pass
            if proc.poll() is None:
                try: proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    stop_process(proc)
                    failure=True
            proc.wait()
            if proc.returncode!=0: failure=True
    except (OSError,ValueError):
        failure=True
    finally:
        if proc is not None:
            if proc.poll() is None: stop_process(proc)
            proc.wait()
            if proc.stdout: proc.stdout.close()
        with lock:
            state="stopped" if job["cancel"] else "failed" if failure or not job["answer"] else "done"
            if state=="done":
                verified_at=int(time.time());retained_auth=True
                persist_auth_metadata()
            job.update(state=state,detail={"stopped":"已停止生成","failed":"模型调用失败或超时，请检查授权、额度及 CLI 事件格式","done":""}[state],proc=None)
            try:
                save_snapshot(job)
                prune_snapshots()
            except OSError:
                # Live result remains available if the disk is temporarily unavailable.
                pass
            chat_active=None

def chat_start(data, video=False, vision=False):
    global chat_active
    if not isinstance(data,dict): return 422,{"detail":"请求无效"}
    ident,model,prompt=data.get("id"),data.get("model"),data.get("prompt")
    if not isinstance(ident,str) or not JOB_ID.fullmatch(ident) or not allowed_model(model) or not isinstance(prompt,str) or "\x00" in prompt or not 0<len(prompt.encode("utf-8"))<=(120000 if video else 100000):
        return 422,{"detail":"模型或上下文无效；请检查模型及提示词长度"}
    attachment=None
    if vision:
        try: attachment=vision_attachment(data.get("attachment"))
        except ValueError: return 422,{"detail":"图片附件无效或超过8 MiB"}
    system,effort,timeout=data.get("system",""),data.get("effort","default"),data.get("timeout",900)
    if effort != "default" and (not isinstance(effort,str) or effort not in catalog_efforts.get(model, [])):
        return 422,{"detail":"当前模型未报告该推理强度，请刷新模型配置"}
    if video and (not isinstance(system,str) or "\x00" in system or len(system.encode("utf-8"))>4096 or effort not in ("default","low","medium","high","xhigh","max") or type(timeout) is not int or not 1<=timeout<=900):
        return 422,{"detail":"视频模型参数无效"}
    exe=executable()
    if not exe: return 503,{"detail":"未安装 Qoder CN CLI"}
    with lock:
        if ident in chat_jobs: return 200,chat_snapshot(chat_jobs[ident])
        cached=load_snapshot(ident)
        if cached: return 200,cached
        if user_disconnected:return 409,{"detail":"已退出本系统 AI，请主动登录"}
        if chat_active or login_process is not None: return 409,{"detail":"当前已有模型任务或授权，请先完成"}
        # Keep a bounded number of completed jobs for reconnecting clients.
        for old in list(chat_jobs)[:-31]:
            if chat_jobs[old]["state"]!="running": del chat_jobs[old]
        job={"id":ident,"state":"running","answer":"","detail":"","proc":None,"cancel":False,"video":video,"system":system,"effort":effort,"timeout":timeout}
        try: save_snapshot(job)
        except OSError: return 503,{"detail":"任务结果缓存不可写，请检查执行服务存储"}
        chat_jobs[ident]=job
        chat_active=ident
        threading.Thread(target=chat_run,args=(job,exe,model,prompt,attachment) if vision else (job,exe,model,prompt),daemon=True).start()
        return 200,chat_snapshot(job)


# The SDK owns the reasoning loop. This subprocess exchanges only MCP calls/results
# with the host; it never receives a database connection or arbitrary shell access.
# Trusted project skills, generated from application-owned definitions only.
NATIVE_SKILLS = {
    "math-intake": "---\nname: math-intake\ndescription: 数学试卷、教材、图片和Word的原文识别、题目录入及逐题审核。\n---\n忠实保留题干、题号、公式、选项和已有答案解析。读取用户指定的完整资料范围，识别连续页之间的题目与解答归属；不可将单页开头续接解析当作新题。数学公式使用标准 LaTeX。题干无法辨认时重新查看原图或如实说明，不猜测。\n对确实缺失的答案解析自动求解，标注 generated_fields，不冒充原文。小问各自有答案和解析，无公共重复解析。解析应可核对、规范分步。知识点与知识标签不同：每道题生成2至5个具体标签，选一个主标签；准确匹配已有标签，不能强行套用。\n使用实际审核草稿工具产生结果，检查题号覆盖及页码。审核前不得正式入库；重新识别须实际读取原件，旧草稿仅在未审核且版本匹配时才能生成替代版本。",
    "math-teaching": "---\nname: math-teaching\ndescription: 数学教研创作、题库检索、讲义教材及组卷设计。\n---\n理解用户的对象、范围、教学目的与实际素材。使用题库真实检索及来源工具，按需查询多个科目、院校、年份和知识标签，不能捏造题库记录。用可靠业务工具生成可编辑的教研草稿；保持原题和引用的真实性。数学表达用LaTeX，教学推导清晰，分值与题型以用户要求为准。需要导出、正式登记或最终审核时，如实说明当前成果。",
    "math-review": "---\nname: math-review\ndescription: 数学题目与解析的完整性、来源对应、重复题及知识标签检查。\n---\n检查实际资料是否全部覆盖、题干与答案解析是否一一对应、公式是否完整、是否出现重复或跨页遗漏。已有知识标签仅在含义和科目准确匹配时复用。区分原文和AI补充，不以推测作为来源。查重候选不是自动判定重复。保留用户人工审核。",
    "math-presentation": "---\nname: math-presentation\ndescription: 微光数学文档排版、封面和教学作品的创作规范。\n---\n沿用用户已有模板和配色。数学公式用LaTeX，版面清晰、不重叠；按实际文档版本局部调整，不修改题库原件。利用现有工具进行封面、排版和作品草稿创作；不虚报已渲染、已导出或已发布。"
}

def install_native_skills(cwd):
    root=cwd/".qoder-cn"/"skills"
    for name,content in NATIVE_SKILLS.items():
        path=root/name/"SKILL.md"
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        path.write_text(content+"\n",encoding="utf-8")

SDK_AGENT_SCRIPT = r"""
import asyncio, json, sys
from uuid import uuid4
from qodercn_agent_sdk import QoderAgentOptions, QoderSDKClient, qodercli_auth, tool, create_sdk_mcp_server, ResultMessage, SystemMessage, AgentDefinition, AssistantMessage, TextBlock
from mcp.types import ToolAnnotations

def emit(value):
    print(json.dumps(value,ensure_ascii=False),flush=True)

async def main():
    cfg=json.loads(sys.stdin.readline())
    serial=asyncio.Lock()
    def define(spec):
        async def call(args):
            async with serial:
                ident=str(uuid4())
                emit({"type":"call","id":ident,"name":spec["name"],"args":args})
                line=await asyncio.to_thread(sys.stdin.readline)
                if not line:raise RuntimeError("host disconnected")
                result=json.loads(line)
                if result.get("id")!=ident:raise RuntimeError("host result mismatch")
                return result["result"]
        annotations=ToolAnnotations(readOnlyHint=not spec.get("write",False),
            destructiveHint=False,openWorldHint=False,maxResultSizeChars=12*1024*1024 if spec["name"]=="native_page" else 240000)
        return tool(spec["name"],spec["description"],spec["parameters"],annotations=annotations)(call)
    server=create_sdk_mcp_server("weiguang",tools=[define(t) for t in cfg["tools"]])
    names=["mcp__weiguang__"+t["name"] for t in cfg["tools"]]
    read_names=["mcp__weiguang__"+t["name"] for t in cfg["tools"] if not t.get("write",False)]
    write_names=[name for name in names if name not in read_names]
    blocked=["Bash","Read","Write","Edit","MultiEdit","Glob","Grep","WebFetch","WebSearch"]
    builtins=["TodoWrite","Skill","Agent"]
    agents={"math-reviewer":AgentDefinition(description="独立检查数学内容、来源、跨页遗漏与知识标签，只读，不创建或修改业务数据。",
        prompt="根据主Agent给出的具体任务检查数学资料或题库内容，使用已授权只读工具，给出可核对的发现，不代替人工审核。",
        tools=read_names,disallowedTools=blocked+write_names,model="inherit",mcpServers=["weiguang"],permissionMode="dontAsk")}
    opts=QoderAgentOptions(auth=qodercli_auth(),cwd=cfg["cwd"],cli_path=cfg["cli"],
        model=cfg["model"],system_prompt=cfg["system"],tools=[*builtins,*names],
        allowed_tools=[*builtins,*names],disallowed_tools=blocked,permission_mode="dontAsk",strict_mcp_config=True,
        setting_sources=["project"],skills=cfg["skills"],agents=agents,mcp_servers={"weiguang":server},
        extra_args={"reasoning-effort":cfg["effort"]} if cfg["effort"]!="default" else {},
        **({"resume":cfg["resume"]} if cfg.get("resume") else {"session_id":cfg["session_id"]}))
    async with QoderSDKClient(options=opts) as client:
        await client.query(cfg["prompt"])
        async for message in client.receive_response():
            if isinstance(message,SystemMessage) and message.subtype=="init":
                emit({"type":"session","session_id":message.data.get("session_id") or cfg.get("resume") or cfg["session_id"]})
            if isinstance(message,AssistantMessage):
                answer="\n".join(block.text for block in message.content if isinstance(block,TextBlock))
                if answer:emit({"type":"assistant","answer":answer[:48000]})
            if isinstance(message,ResultMessage):
                emit({"type":"result","success":message.subtype=="success","answer":message.result or "",
                      "session_id":message.session_id})
                return
    emit({"type":"result","success":False,"answer":""})

try:asyncio.run(main())
except Exception as exc:
    # Do not leak prompts, credentials or raw tool payloads into logs/UI.
    emit({"type":"error","detail":"原生 Agent SDK 执行失败："+type(exc).__name__})
    sys.exit(1)
"""

def agent_start(data):
    global chat_active
    if not isinstance(data,dict):return 422,{"detail":"原生Agent请求无效"}
    ident,workspace,session=data.get("id"),data.get("workspace"),data.get("session_id")
    resume=data.get("resume")
    model,effort,prompt,system=data.get("model"),data.get("effort","default"),data.get("prompt"),data.get("system")
    specs=data.get("tools")
    def uid(value):return isinstance(value,str) and bool(JOB_ID.fullmatch(value))
    if not all(uid(x) for x in (ident,workspace,session)) or (resume is not None and not uid(resume)):
        return 422,{"detail":"原生会话编号无效"}
    if not allowed_model(model) or effort!="default" and effort not in catalog_efforts.get(model,[]):
        return 422,{"detail":"模型或推理强度无效"}
    if not isinstance(prompt,str) or not 0<len(prompt.encode())<=100000 or not isinstance(system,str) or len(system.encode())>80000:
        return 422,{"detail":"原生Agent上下文无效"}
    if not isinstance(specs,list) or not 0<len(specs)<=100 or any(not isinstance(t,dict) or not isinstance(t.get("name"),str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}",t["name"]) or not isinstance(t.get("description"),str) or not isinstance(t.get("parameters"),dict) for t in specs):
        return 422,{"detail":"业务工具目录无效"}
    if len({t["name"] for t in specs})!=len(specs):return 422,{"detail":"业务工具重复"}
    exe=executable()
    if not exe or not SDK_PYTHON.is_file():return 503,{"detail":"原生Agent SDK尚未安装"}
    with lock:
        if ident in chat_jobs:return 200,chat_snapshot(chat_jobs[ident])
        cached=load_snapshot(ident)
        if cached:return 200,cached
        if user_disconnected:return 409,{"detail":"已退出AI，请先登录"}
        if chat_active or login_process is not None:return 409,{"detail":"当前已有模型任务或授权，请先完成"}
        for old in list(chat_jobs)[:-31]:
            if chat_jobs[old]["state"]!="running":del chat_jobs[old]
        job={"id":ident,"state":"running","answer":"","detail":"原生Agent正在执行","proc":None,"cancel":False,"native":True}
        try:save_snapshot(job)
        except OSError:return 503,{"detail":"原生Agent任务缓存不可写"}
        chat_jobs[ident]=job;chat_active=ident
        threading.Thread(target=agent_run,args=(job,{**data,"cli":exe}),daemon=True).start()
        return 200,chat_snapshot(job)

def agent_run(job,cfg):
    global chat_active,verified_at,retained_auth
    proc=None;success=False;detail=""
    try:
        cwd=Path.home()/".jiaoyan-native-workspaces"/cfg["workspace"]
        cwd.mkdir(mode=0o700,parents=True,exist_ok=True)
        install_native_skills(cwd)
        proc=subprocess.Popen([str(SDK_PYTHON),"-u","-c",SDK_AGENT_SCRIPT],cwd=cwd,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
        with lock:
            job["proc"]=proc
            if job["cancel"]:stop_process(proc)
        proc.stdin.write((json.dumps({**cfg,"cwd":str(cwd),"skills":list(NATIVE_SKILLS)},ensure_ascii=False)+"\n").encode());proc.stdin.flush()
        deadline=time.monotonic()+1200;buf=b""
        names={t["name"] for t in cfg["tools"]}
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout,selectors.EVENT_READ)
            while time.monotonic()<deadline:
                with lock:
                    if job["cancel"]:break
                if not sel.select(.25):
                    if proc.poll() is not None:break
                    continue
                chunk=os.read(proc.stdout.fileno(),65536)
                if not chunk:break
                buf+=chunk
                if len(buf)>2_000_000:raise ValueError("SDK event too large")
                while b"\n" in buf:
                    raw,buf=buf.split(b"\n",1)
                    event=json.loads(raw)
                    kind=event.get("type")
                    with lock:
                        if kind=="call":
                            if job.get("pending") or event.get("name") not in names or not JOB_ID.fullmatch(str(event.get("id",""))) or not isinstance(event.get("args"),dict):raise ValueError("invalid MCP call")
                            job["pending"]={k:event[k] for k in ("id","name","args")}
                            job["detail"]="等待微光数学业务工具"
                        elif kind in ("session","result"):
                            sid=event.get("session_id")
                            if isinstance(sid,str) and JOB_ID.fullmatch(sid):
                                job["native_session"]=sid
                            if kind=="result":
                                success=event.get("success") is True
                                job["answer"]=str(event.get("answer") or "")[:48000]
                        elif kind=="assistant":
                            job["answer"]=str(event.get("answer") or "")[:48000]
                        elif kind=="error":
                            detail=str(event.get("detail",""))[:200]
                if success:break
            else:detail="原生Agent执行超时"
    except (OSError,ValueError,TypeError,KeyError) as exc:
        detail="原生Agent通信失败："+type(exc).__name__
    finally:
        if proc:
            if proc.poll() is None:
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:stop_process(proc)
            proc.wait()
            if proc.stdin:proc.stdin.close()
            if proc.stdout:proc.stdout.close()
        with lock:
            state="stopped" if job["cancel"] else "done" if success and proc and proc.returncode==0 else "failed"
            if state=="done":
                verified_at=int(time.time());retained_auth=True;persist_auth_metadata()
            job.update(state=state,detail=detail or ("原生Agent执行完成" if state=="done" else "原生Agent已停止或失败"),proc=None)
            job.pop("pending",None)
            try:save_snapshot(job);prune_snapshots()
            except OSError:pass
            chat_active=None

def agent_reply(ident,data):
    if not isinstance(data,dict) or not isinstance(data.get("id"),str) or not isinstance(data.get("result"),dict):
        return 422,{"detail":"工具结果无效"}
    with lock:
        job=chat_jobs.get(ident)
        if not job or not job.get("native") or job["state"]!="running":return 409,{"detail":"原生任务已停止"}
        if job.get("last_reply")==data["id"]:return 200,chat_snapshot(job)
        pending=job.get("pending")
        if not pending or pending["id"]!=data["id"] or not job.get("proc"):return 409,{"detail":"工具调用已变化"}
        try:
            job["proc"].stdin.write((json.dumps(data,ensure_ascii=False)+"\n").encode())
            job["proc"].stdin.flush()
        except (OSError,ValueError):return 503,{"detail":"原生Agent工具结果未送达"}
        job["last_reply"]=data["id"];job.pop("pending",None);job["detail"]="原生Agent正在继续工作"
        return 200,chat_snapshot(job)


def chat_state(ident, cancel=False):
    with lock:
        job=chat_jobs.get(ident)
        if not job:
            cached=load_snapshot(ident)
            return (200,cached) if cached else (404,{"detail":"执行任务不存在或结果已过期"})
        if cancel and job["state"]=="running":
            job["cancel"]=True
            if job["proc"]: stop_process(job["proc"])
        return 200,chat_snapshot(job,live=True)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def reply(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
    def do_GET(self):
        if self.path == "/status":
            return self.reply(200, status())
        if self.path.startswith("/chat/"):
            return self.reply(*chat_state(self.path.removeprefix("/chat/")))
        if self.path == "/models":
            return self.reply(200, model_catalog())
        if self.path == "/usage":
            return self.reply(*usage_status())
        return self.reply(404, {"detail": "Not found"})
    def do_POST(self):
        if self.path.startswith("/chat/") and self.path.endswith("/cancel"):
            return self.reply(*chat_state(self.path.split("/")[2], True))
        if self.path=="/agent/start" or self.path.startswith("/agent/") and self.path.endswith("/tool-result"):
            try:
                n=int(self.headers.get("Content-Length","0"))
                if not 0<n<=12*1024*1024:raise ValueError()
                data=json.loads(self.rfile.read(n))
            except (ValueError,UnicodeError):return self.reply(422,{"detail":"原生Agent请求无效"})
            if self.path=="/agent/start":return self.reply(*agent_start(data))
            return self.reply(*agent_reply(self.path.split("/")[2],data))
        if self.path in ("/chat/start", "/video/start", "/vision/start"):
            try:
                n=int(self.headers.get("Content-Length","0"))
                if not 0<n<=(12*1024*1024 if self.path=="/vision/start" else 800000 if self.path == "/video/start" else 200000): raise ValueError()
                data=json.loads(self.rfile.read(n))
            except (ValueError,UnicodeError): return self.reply(422,{"detail":"请求无效"})
            return self.reply(*chat_start(data, video=self.path == "/video/start", vision=self.path=="/vision/start"))
        if self.path == "/models/refresh":
            return self.reply(*refresh_models())
        if self.path == "/usage/refresh":
            return self.reply(*usage_status(True))
        if self.path == "/login/start":
            return self.reply(*start_login())
        if self.path == "/login/cancel":
            return self.reply(200, cancel_login())
        if self.path == "/login/disconnect":
            return self.reply(*disconnect())
        if self.path != "/test":
            return self.reply(404, {"detail": "Not found"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= 64000:
                raise ValueError()
            data = json.loads(self.rfile.read(n))
            model, prompt = data["model"], data["prompt"]
            if not allowed_model(model) or not isinstance(prompt, str) or not 0 < len(prompt.strip()) <= 12000:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            return self.reply(422, {"detail": "参数不正确"})
        return self.reply(*invoke(model, prompt))

class Server(socketserver.UnixStreamServer):
    def get_request(self):
        conn, addr = super().get_request()
        conn.settimeout(5)
        return conn, addr

if __name__ == "__main__":
    if os.geteuid() == 0:
        raise SystemExit("Do not run as root")
    restore_auth_state()
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    with Server(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o660)
        server.serve_forever()
