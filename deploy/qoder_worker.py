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

def sdk_environment():
    """Keep login environment, but let SDK choose its bundled compatible CLI."""
    env=dict(os.environ)
    env.pop("QODERCN_PATH",None)
    return env
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
                env=sdk_environment())
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
                env=sdk_environment())
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
        MODEL_WAITERS.clear()
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

# Static SDK compatibility probe (no model calls or account data).
NATIVE_SDK_CHECK = "import inspect,json\nfrom qodercn_agent_sdk import QoderAgentOptions,QoderSDKClient,qodercli_auth,tool,create_sdk_mcp_server,ResultMessage,SystemMessage,AgentDefinition,AssistantMessage,TextBlock,SDKMirrorErrorMessage\nfrom mcp.types import ToolAnnotations\nparams=inspect.signature(QoderAgentOptions).parameters\nrequired={\"auth\",\"cli_path\",\"cwd\",\"model\",\"system_prompt\",\"session_id\",\"resume\",\"session_store\",\"session_store_flush\",\"tools\",\"allowed_tools\",\"disallowed_tools\",\"permission_mode\",\"setting_sources\",\"skills\",\"agents\",\"mcp_servers\",\"strict_mcp_config\",\"extra_args\",\"include_partial_messages\"}\nmissing=sorted(required-set(params))\nasync def ping(args):\n    return {\"content\":[{\"type\":\"text\",\"text\":\"ok\"}]}\nannotations=ToolAnnotations(readOnlyHint=True,maxResultSizeChars=12000000)\nmcp=create_sdk_mcp_server(\"probe\",tools=[tool(\"ping\",\"probe\",{\"type\":\"object\",\"properties\":{}},annotations=annotations)(ping)])\nagent=AgentDefinition(description=\"probe\",prompt=\"probe\",tools=[],disallowedTools=[\"Bash\"],model=\"inherit\",mcpServers=[\"probe\"],permissionMode=\"dontAsk\")\nQoderAgentOptions(tools=[\"Agent\",\"Skill\",\"mcp__probe__ping\"],allowed_tools=[\"Agent\",\"Skill\",\"mcp__probe__ping\"],setting_sources=[],skills=[],agents={\"probe\":agent},mcp_servers={\"probe\":mcp},permission_mode=\"dontAsk\",session_store_flush=\"eager\")\nmethods=all(callable(getattr(QoderSDKClient,k,None)) for k in (\"query\",\"receive_response\",\"get_server_info\"))\nprint(json.dumps({\"ready\":not missing and methods,\"memory\":\"memory\" in params and callable(getattr(QoderSDKClient,\"flush_memory\",None)),\"missing\":missing}))\n"
native_sdk_info={"ready":False,"memory":False,"reason":"not_checked"}

def check_native_sdk():
    if not SDK_PYTHON.is_file():return {"ready":False,"memory":False,"reason":"sdk_missing"}
    try:
        result=subprocess.run([str(SDK_PYTHON),"-c",NATIVE_SDK_CHECK],capture_output=True,timeout=15,check=False)
        if result.returncode or len(result.stdout)>16000:return {"ready":False,"memory":False,"reason":"sdk_incompatible"}
        value=json.loads(result.stdout)
        if not isinstance(value,dict):raise ValueError()
        return {"ready":value.get("ready") is True,"memory":value.get("memory") is True,
            "reason":"ready" if value.get("ready") is True else "sdk_incompatible"}
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return {"ready":False,"memory":False,"reason":"sdk_probe_failed"}

# FIFO admission for callers that already retry with a stable job ID.
# No queued prompts or images are held in the Worker; callers own their durable jobs.
MODEL_WAITERS={}
MODEL_WAIT_TTL=30.0
MODEL_WAIT_MAX=128

def prune_model_waiters(at=None):
    at=time.monotonic() if at is None else at
    for ident,seen in list(MODEL_WAITERS.items()):
        if at-seen>MODEL_WAIT_TTL:MODEL_WAITERS.pop(ident,None)

def model_admission(ident,waiting=False,at=None):
    """Call under the Worker lock. A free slot is reserved in arrival order."""
    at=time.monotonic() if at is None else at
    prune_model_waiters(at)
    if waiting:
        if ident not in MODEL_WAITERS and len(MODEL_WAITERS)>=MODEL_WAIT_MAX:return False
        MODEL_WAITERS[ident]=at
    if chat_active or login_process is not None:return False
    if MODEL_WAITERS and next(iter(MODEL_WAITERS))!=ident:return False
    MODEL_WAITERS.pop(ident,None)
    return True

def status():
    with lock:
        prune_model_waiters()
        available = bool(executable())
        return {"available": available, "detail": "CLI 已安装" if available else "未检测到 qoderclicn",
                "verified_at": verified_at, "login": dict(login), "auth_ui": True, "model_discovery": True, "worker_version": 24, "waiting_count":len(MODEL_WAITERS), "native_video":native_video_enabled() and native_sdk_info["ready"], "native_agent":native_sdk_info["ready"], "native_sdk":dict(native_sdk_info), "vision_attachment": True, "usage_discovery":True, "retained_auth":retained_auth,"user_disconnected":user_disconnected, "video_inference": True, "busy": bool(chat_active or login_process is not None), "chat_available": available and not user_disconnected, "durable_results": True}

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
    if job.get("video"):result["video_inference_mode"]="native_sdk" if job.get("native_video") else "legacy_cli"
    elif job.get("video_inference_mode"):result["video_inference_mode"]=job["video_inference_mode"]
    for key in ("native_memory","native_memory_flush","native_mirror_error","native_interrupted","failure_reason"):
        if key in job:result[key]=job[key]
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
            value.update(state="failed",failure_reason="worker_restart",detail="执行服务已重启；保留已写入的结果")
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

# Independently opt in after real SDK/video regression validation.
def native_video_enabled():
    return os.environ.get("WG_NATIVE_VIDEO")=="1"

SDK_VIDEO_SCRIPT = "import asyncio,json,sys,inspect\nfrom qodercn_agent_sdk import QoderAgentOptions,QoderSDKClient,qodercli_auth,ResultMessage,AssistantMessage,TextBlock\ndef emit(event):\n    print(json.dumps(event,ensure_ascii=False),flush=True)\nasync def main():\n    cfg=json.loads(sys.stdin.readline())\n    extra={\"no-session-persistence\":None}\n    if cfg[\"effort\"]!=\"default\":extra[\"reasoning-effort\"]=cfg[\"effort\"]\n    # Preserve the original video prompt; no extra skills, memory or tool actions.\n    opts={\"auth\":qodercli_auth(),\"cwd\":cfg[\"cwd\"],\n          \"model\":cfg[\"model\"],\"tools\":[],\"allowed_tools\":[],\n          \"setting_sources\":[],\"skills\":[],\"strict_mcp_config\":True,\n          \"permission_mode\":\"dontAsk\",\"extra_args\":extra,\"include_partial_messages\":True}\n    if cfg[\"system\"]:opts[\"system_prompt\"]=cfg[\"system\"]\n    if \"memory\" in inspect.signature(QoderAgentOptions).parameters:opts[\"memory\"]={}\n    final=None\n    async with QoderSDKClient(options=QoderAgentOptions(**opts)) as client:\n        await client.query(cfg[\"prompt\"])\n        async for message in client.receive_response():\n            if isinstance(message,AssistantMessage):\n                value=\"\".join(b.text for b in message.content if isinstance(b,TextBlock))\n                if value:emit({\"type\":\"assistant\",\"message\":{\"content\":value}})\n            elif isinstance(message,ResultMessage):\n                final={\"type\":\"result\",\"is_error\":message.subtype!=\"success\" or not isinstance(message.result,str) or not message.result.strip(),\"result\":message.result or \"\"}\n                break\n            elif isinstance(getattr(message,\"event\",None),dict):\n                event=message.event\n                if event.get(\"type\")==\"content_block_delta\" and event.get(\"delta\",{}).get(\"type\")==\"text_delta\":\n                    emit({\"type\":\"stream_event\",\"event\":event})\n    emit(final or {\"type\":\"error\"})\n    if not final or final[\"is_error\"]:sys.exit(1)\ntry:asyncio.run(main())\nexcept Exception:\n    emit({\"type\":\"error\"})\n    sys.exit(1)\n"

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
            native=video and job.get("native_video",False)
            if native:
                proc=subprocess.Popen([str(SDK_PYTHON),"-u","-c",SDK_VIDEO_SCRIPT],cwd=cwd,
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,env=sdk_environment())
            else:
                proc=subprocess.Popen(args+["-p",prompt],cwd=cwd,stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            with lock:
                job["proc"]=proc
                if job["cancel"]:stop_process(proc)
            if native:
                try:
                    proc.stdin.write((json.dumps({"cwd":cwd,"model":model,"effort":job["effort"],
                        "system":job["system"],"prompt":prompt},ensure_ascii=False)+"\n").encode())
                    proc.stdin.flush()
                finally:proc.stdin.close()
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
    native_video=bool(video and native_video_enabled())
    if native_video and not native_sdk_info["ready"]:return 503,{"detail":"视频原生SDK接口未通过检查"}
    with lock:
        if ident in chat_jobs: return 200,chat_snapshot(chat_jobs[ident])
        cached=load_snapshot(ident)
        if cached: return 200,cached
        if user_disconnected:return 409,{"detail":"已退出本系统 AI，请主动登录"}
        if not model_admission(ident,waiting=bool(video or data.get("queue_wait") is True)): return 409,{"detail":"当前已有模型任务或授权，按队列等待"}
        # Keep a bounded number of completed jobs for reconnecting clients.
        for old in list(chat_jobs)[:-31]:
            if chat_jobs[old]["state"]!="running": del chat_jobs[old]
        job={"id":ident,"state":"running","answer":"","detail":"","proc":None,"cancel":False,"video":video,"system":system,"effort":effort,"timeout":timeout,"native_video":native_video}
        try: save_snapshot(job)
        except OSError: return 503,{"detail":"任务结果缓存不可写，请检查执行服务存储"}
        chat_jobs[ident]=job
        chat_active=ident
        threading.Thread(target=chat_run,args=(job,exe,model,prompt,attachment) if vision else (job,exe,model,prompt),daemon=True).start()
        return 200,chat_snapshot(job)


# The SDK owns the reasoning loop. This subprocess exchanges only MCP calls/results
# with the host; it never receives a database connection or arbitrary shell access.
# Trusted project skills. Canonical files: skills/<name>/SKILL.md.
# Embedded for standalone worker deployment; CI verifies exact parity.
NATIVE_SKILLS = {
    "math-solving": "---\nname: math-solving\ndescription: 数学答疑、计算、证明、公式推导、答案解析补充、多解法分析及结果核对。\n---\n\n# 数学求解\n## 执行规则\n1. 完整理解题干、已知条件、求解目标及所属学科。\n2. 根据题目结构自主选择方法，不机械套用固定模板。\n3. 优先严谨、直接、易懂、符合考试习惯的方法。\n4. 保留原题记号，避免不必要的新变量及辅助函数。\n5. 应用定理、公式或等价变形前核对适用条件。\n6. 按需核查定义域、参数范围、端点、特殊值及分类讨论。\n7. 完整展示关键推导与依据，不以“显然”“易得”代替必要步骤。\n8. 必要时使用代入、求导、逆运算、特殊值或独立方法验证结果。\n9. 仅在有实际教学价值时提供多种解法。\n10. 按用户要求调整讲解深度；无法可靠求解时如实说明。\n## 正式题库答案解析\n答案仅保存最终结果；计算题以“解：”开始，证明题以“证明：”开始；各小问分别提供答案解析。短式行内 LaTeX、长式独立展示，连续推导对齐等号或不等号。正式解析遵循系统已有 answer_format.py 契约，不另设思路、易错点、总结及口播模块。聊天答疑可按用户要求解释这些内容。\n## 工具与边界\n按需调用 question_search、resource_read、resource_methods、knowledge_search。普通数学答疑无需强制检索。不得编造定理结论、强推错误参考答案或擅改题库原有答案解析；不引入 SymPy；不将数学正确性检查加入视频渲染流程。",
    "math-intake": "---\nname: math-intake\ndescription: PDF、Word、图片、文本识别和原始资料库读取，历史续接、数学题目及知识点录入、缺失解析补充和审核草稿。\n---\n\n# 资料识别与录入\n## 执行规则\n1. 理解用户指定资料、识别范围及录入目标，支持多文件混合任务。\n2. 读取实际原件，不凭文件名猜测；PDF 每批最多10个物理页，不超授权范围。\n3. 继续识别前读取实际进度、上一批结尾和已整理题目。\n4. 根据双栏、表格、答案框等版面判断阅读顺序；Word 先读正文及图片数量，再逐张读取所需原图。\n5. 忠实保留题号、题干、选项、公式、原有分段及已有解析，正确合并跨页题目及解析，不把续接解析当成新题。\n6. 重点复核分数、根号范围、积分上下限、矩阵、正负号等；只重读疑问局部，避免全量重复识别。\n7. 保持图形、表格、图注与题干关联；无法可靠提取时标明原图待核对，不伪造图形或题干。\n8. 各题独立识别科目；知识点是原文实际定义、定理、公式、证明等，不自动编造证明。\n9. 仅对缺失答案解析自动求解补齐，无需额外确认；保留原有数学内容。\n10. 分离的题目及答案解析资料先核对题干、条件及题号，保存真实参考文件、页码及字段来源，不能仅凭同题号匹配；找不到可靠参考原文才自动补充。\n11. AI 补充字段用 generated_fields 标记 answer 或 solution；不冒充原文，无法可靠求解时留空并说明阻碍，不强行提交不完整草稿。\n12. 多小问各自有答案和解析，无公共重复解析，多空逐一对应。\n13. 每题生成2—5个准确知识标签并确定一个主标签；按需结合数学求解、知识关联与审核技能。\n14. 提交前检查题号覆盖、跨页边界、页码及解析对应，不将未完成边界题冒充完整题。\n15. 重做未审核旧批次必须实际读原件、携带旧任务ID及revision，保留旧版本；不覆盖已审核批次。\n16. 使用真实工具生成待人工审核草稿，不自行正式入库。\n## 工具与边界\noriginal_search 查找历史资料；native_workspace 读取附件和进度；native_attach 关联真实文件ID；native_page 读取原页、Word段落及图片；native_batch_context 核对已有批次；native_intake_review 创建附件审核草稿；native_text_review 仅用于用户直接提供的纯文字或明确创作的题目，不代替附件读取；intake_status 查询真实状态。\n只使用当前模式开放的工具，不重复录入、不超范围、不绕过审核及版本保护。",
    "math-review": "---\nname: math-review\ndescription: 数学内容核对、原文覆盖、跨页遗漏、题目完整性、答案解析、查重候选及知识标签审核。\n---\n\n# 数学内容审核\n## 执行规则\n- 确定审核对象和范围，使用真实题目、原件、解析及题库记录。\n- 检查条件、选项、小问、图形、公式、题号是否遗漏；核对跨页衔接、题干与答案解析一一对应。\n- 区分原文、真实参考资料及 AI 补充内容；检查 AI 生成解析的推导逻辑、定理条件及计算结果，必要时重新求解。\n- 区分相同题干、同题新增解法、答案冲突和相似题；公式结构相似不代表数学等价；同题新增解法优先考虑复用原题和通过现有流程追加解法。\n- 核查知识标签准确性、重复性、粒度及主考点；仅准确匹配科目和含义时复用。\n- 指明问题位置、原因、证据及建议：遗漏则补读，识别错误则定位复核，AI 计算错误则重新求解，原文冲突由用户核对；不确定时如实说明。\n- 必要时调用现有 math-reviewer 只读子智能体独立核对；不重复审核未发生变化的已核对内容。\n## 工具与边界\nresource_read、resource_methods、related_questions、question_search、tag_search、native_page、native_batch_context、native_read_detail。只使用实际开放工具；检索返回候选，不冒充正式查重，正式查重仍由现有业务审核完成。不替代人工最终审核，不擅改确认内容，不用于视频生成后的数学正确性校验。",
    "math-knowledge": "---\nname: math-knowledge\ndescription: 题库与公式检索、知识点查询、知识标签生成、主考点识别、相关题及解法关联、院校年份来源统计。\n---\n\n# 知识关联与题库检索\n## 执行规则\n- 理解学科、题型、难度、知识范围、院校、年份及来源，组合实际筛选条件，不局限单关键词；按需分页，不把局部查询冒充全量。\n- 知识点是定义、定理、公式、证明等实际教学内容；知识标签是分类关联名称，严格区分。\n- 根据实际求解过程确定核心考点，不只提取题干中的数学名词；每题生成2—5个具体、不重复的知识标签，其中一个为主标签。\n- 优先复用科目与数学含义完全匹配的正式名称或准确别名；无合适标签时提出新标签候选；避免宽泛、重复、无分类价值标签。\n- 根据共同考点、解题方法和数学结构检索相关题；区分知识相关、方法相关、题干相似与重复题。\n- 按实际院校、年份、来源、考试类别统计；区分唯一题目数及来源—题目关联数，明确数据范围和可确认的资料录入完整程度；不把未录入试卷教材当作已统计。\n- 示例：泰勒公式求极限可采用泰勒公式为主标签、极限计算和高阶无穷小为辅标签（须符合实际推导），不泛化为“数学题”“公式”。\n## 工具与边界\nquestion_search、formula_search、knowledge_search、tag_search、tag_neighbors、related_questions、resource_methods、source_search、source_questions、source_statistics。不编造题库记录或统计，不把公式结构相似当成等价证明，不虚构考试考查预测，不绕过权限修改知识图谱。",
    "math-teaching": "---\nname: math-teaching\ndescription: 教学研究、训练方案、基于真实题库的选题组合、组卷、组讲义、组教材及教学资料整理。\n---\n\n# 教学教研与资料组编\n## 执行规则\n- 理解教学目标、学生基础、考试类型及用途，确定知识覆盖、题型及方法。仅在用户要求 AI 参与时协助组编，不干预手动流程。\n- 从真实题库及知识库检索；按需安排基础、强化、综合训练，选择符合教学目标的难度、知识跨度及顺序。\n- 兼顾知识覆盖、典型性及方法多样性；避免大量考点和解法完全重复的题，专项重复训练除外。\n- 题量、分值、题型比例以用户要求为准，不固定难度比例和结构。\n- 组卷注意题型、分值和难度；组讲义按用途组织知识、例题和练习；组教材按知识前置关系组织章节及小节。\n- 优先复用现有资源，保留原题、解析、来源和真实引用；用户明确要求新题时按数学求解规范生成待审核内容，不冒充已有记录。\n- 追加或修改先读取当前版本，保留未涉及内容，使用实际业务工具创建可编辑草稿；据实汇报成果、覆盖及不足。\n## 可选策略\n基础讲义重知识理解与基本方法；强化讲义重方法选择及变式；专题训练集中突破考点；模拟试卷平衡题型、分值和难度；历年真题保持来源及原题；教材注意知识体系及衔接。按需选用，不强制套模板。\n## 工具与边界\nquestion_search、knowledge_search、source_statistics、related_questions、selection_create、book_create、chapter_create、document_append、chapter_order、document_read、document_patch。不虚构题目、不改题库原件、不把草稿报告为已正式导出；最终审核及导出走现有流程。",
    "math-presentation": "---\nname: math-presentation\ndescription: 试卷讲义教材及原始来源排版、模板复用、版面检查、品牌封面设计、教学作品查询。\n---\n\n# 文档排版与封面\n## 文档规则\n- 理解用途、结构、排版要求，优先复用已有文档模板和设置；标题、章节、正文、例题、答案解析层次清晰。\n- 数学公式使用标准 LaTeX，多行推导对齐等号或不等号，长式按数学语义合理换行。\n- 避免题干与选项、图形、必要条件不合理分离，避免页尾孤立标题、公式截断、文字重叠和大片无意义留白，不靠过度缩小字号解决分页。\n- 局部编辑先读取真实文档、块编号和排版revision，仅调整用户指定内容、样式及允许字段；不改变原题数学含义，不擅改引用、图形、编号及文档结构。\n- 具有实际预览能力时核对版面；无法查看时说明未视觉检查，不声称通过。使用现有 PDF 正式导出流程，由用户确认，不新增 Word 导出系统。\n## 封面规则\n- 沿用已有 Logo、品牌配色及视觉风格；按用户指定平台查询实际尺寸预设，优先复用已有模板。\n- 按题目或作品设计信息层次，突出主要信息，辅助信息简洁；公式清晰，题干引用真实题目。\n- 采用可编辑图层，间距合理、不重叠、不越界，生成可继续调整的封面草稿，不把草稿当成成品或自动发布。\n## 作品管理\n查询真实作品、来源及版本；区分创作文档、制作草稿与正式成品，不虚报归档、导出或发布。\n## 工具与边界\ndocument_search、document_read、document_patch、layout_read、template_search、template_apply、layout_update、cover_presets、cover_templates、cover_create、cover_search、work_search、work_read。仅用实际开放工具，不擅改题库原件或绕过版本保护。",
    "video-workflow": "---\nname: video-workflow\ndescription: 独立视频引擎项目创建、生成、状态查询、自然语言微调、失败重试及作品查询；不负责教学代码编排。\n---\n\n# 视频任务操作\n## 执行规则\n- 理解用户制作或修改对象；查询真实题库题目及推荐解析，使用有效题目版本；创建前检查对应项目，不重复创建。\n- 使用现有独立视频引擎，保留七份教学与技术提示词；题目、答案解析及用户补充要求由现有适配器传递。\n- 提交代码生成后由原引擎校验及自动渲染，不重复提交自动安排的渲染。\n- 提交异步任务后结束本轮释放模型，由系统追踪实际状态，不循环占用模型等待成片。\n- 区分排队、生成、校验、渲染、完成及失败；只有真实渲染成功才报告成片完成，失败根据实际任务状态调用重试工具，不盲目重放。\n- 微调保留用户原始指令，准确确定项目及范围；指定位置只改该处，无指定范围由原编辑器处理全部匹配位置；纯读音交原编辑器修改对应 tts_text，与源码无关或无匹配目标不改变代码；保留未涉及的画面及教学内容。\n- 最终审核、封面设置及归档使用现有人工流程，已审核归档视频不擅改。\n## 工具与边界\nvideo_search、video_read、video_create、video_generate、video_code、video_edit、video_history、video_job_read、video_retry、video_render（仅实际需要独立渲染且未自动安排时调用）。查询归档作品可用 work_search、work_read。\n不替换原教学提示词，不通过工作Agent重生成Manim教学代码，不增加数学正确性审核，不绕过独立引擎，不改固定视频参数，不注入聊天记忆或额外Skill到视频生成通道，不把提交任务当成成片。",
}

def install_native_skills(cwd):
    root=cwd/".qoder-cn"/"skills"
    for name,content in NATIVE_SKILLS.items():
        path=root/name/"SKILL.md"
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        path.write_text(content+"\n",encoding="utf-8")

# Shared by the SDK subprocess and local regression tests; no third-party storage dependency.
SDK_SESSION_STORE_SCRIPT = "import asyncio\nimport hashlib\nimport json\nimport sqlite3\nimport time\nfrom pathlib import Path\n\ndef session_key(key):\n    def get(name,default=None):\n        return key.get(name,default) if isinstance(key,dict) else getattr(key,name,default)\n    project,session,subpath=get(\"project_key\"),get(\"session_id\"),get(\"subpath\") or \"\"\n    if not isinstance(project,str) or not project or not isinstance(session,str) or not session or not isinstance(subpath,str):\n        raise ValueError(\"invalid SDK session key\")\n    if subpath and (subpath.startswith(\"/\") or any(p in (\"\",\".\",\"..\") for p in subpath.split(\"/\")) or \"\\\\\" in subpath):\n        raise ValueError(\"invalid SDK transcript subpath\")\n    return project,session,subpath\n\nclass NativeSessionStore:\n    \"\"\"Opaque SDK transcript mirror, one SQLite file per app conversation.\n    Only the SDK interprets entries. Ordered atomic append and exact replay deduplication.\n    No credentials, business database access, or prompt reconstruction.\n    \"\"\"\n    def __init__(self,path):\n        self.path=Path(path)\n        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)\n        self.path.touch(mode=0o600,exist_ok=True)\n        self.path.chmod(0o600)\n        with self.connect() as db:\n            db.execute(\"CREATE TABLE IF NOT EXISTS entries (seq INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, session TEXT NOT NULL, subpath TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL, mtime INTEGER NOT NULL, UNIQUE(project,session,subpath,digest))\")\n    def connect(self):\n        db=sqlite3.connect(self.path,timeout=20)\n        db.execute(\"PRAGMA busy_timeout=20000\")\n        db.execute(\"PRAGMA secure_delete=ON\")\n        return db\n    def _append(self,key,entries):\n        prefix=session_key(key)\n        rows=[]\n        for entry in entries:\n            raw=json.dumps(entry,ensure_ascii=False,separators=(\",\",\":\"),sort_keys=True,allow_nan=False)\n            # SDK may retry exactly the same serialized transcript entry.\n            digest=hashlib.sha256(raw.encode()).hexdigest()\n            rows.append((*prefix,digest,raw,int(time.time()*1000)))\n        db=self.connect()\n        try:\n            with db:\n                db.execute(\"BEGIN IMMEDIATE\")\n                db.executemany(\"INSERT OR IGNORE INTO entries(project,session,subpath,digest,payload,mtime) VALUES(?,?,?,?,?,?)\",rows)\n        finally:db.close()\n    async def append(self,key,entries):\n        await asyncio.to_thread(self._append,key,entries)\n    def _load(self,key):\n        db=self.connect()\n        try:\n            rows=db.execute(\"SELECT payload FROM entries WHERE project=? AND session=? AND subpath=? ORDER BY seq\",session_key(key)).fetchall()\n            return [json.loads(row[0]) for row in rows] if rows else None\n        finally:db.close()\n    async def load(self,key):\n        return await asyncio.to_thread(self._load,key)\n    def _list_subkeys(self,key):\n        project,session,_=session_key(key)\n        db=self.connect()\n        try:return [row[0] for row in db.execute(\"SELECT DISTINCT subpath FROM entries WHERE project=? AND session=? AND subpath<>'' ORDER BY subpath\",(project,session))]\n        finally:db.close()\n    async def list_subkeys(self,key):\n        return await asyncio.to_thread(self._list_subkeys,key)\n    def _delete(self,key):\n        project,session,subpath=session_key(key)\n        db=self.connect()\n        try:\n            with db:\n                if subpath:db.execute(\"DELETE FROM entries WHERE project=? AND session=? AND subpath=?\",(project,session,subpath))\n                else:db.execute(\"DELETE FROM entries WHERE project=? AND session=?\",(project,session))\n        finally:db.close()\n    async def delete(self,key):\n        await asyncio.to_thread(self._delete,key)\n"

SDK_AGENT_SCRIPT = SDK_SESSION_STORE_SCRIPT + r"""
import asyncio, json, sys, inspect, signal
from uuid import uuid4
from qodercn_agent_sdk import QoderAgentOptions, QoderSDKClient, qodercli_auth, tool, create_sdk_mcp_server, ResultMessage, SystemMessage, AgentDefinition, AssistantMessage, TextBlock, SDKMirrorErrorMessage
from mcp.types import ToolAnnotations

def emit(value):
    print(json.dumps(value,ensure_ascii=False),flush=True)

async def main():
    cfg=json.loads(sys.stdin.readline())
    # Nonblocking pipe reads are cancellable; do not strand an executor thread
    # waiting on stdin if an MCP call and an interrupt race.
    reader=asyncio.StreamReader(limit=13*1024*1024)
    transport,_=await asyncio.get_running_loop().connect_read_pipe(lambda:asyncio.StreamReaderProtocol(reader),sys.stdin.buffer)
    serial=asyncio.Lock()
    interrupt_requested=False
    def define(spec):
        async def call(args):
            async with serial:
                if interrupt_requested:return {"is_error":True,"content":[{"type":"text","text":"当前轮已被用户新指令中断，未执行工具。"}]}
                ident=str(uuid4())
                emit({"type":"call","id":ident,"name":spec["name"],"args":args})
                line=await reader.readline()
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
    params=inspect.signature(QoderAgentOptions).parameters
    if "session_store" not in params:raise RuntimeError("SDK session_store unavailable")
    store=NativeSessionStore(Path(cfg["cwd"])/"session-mirror.sqlite3")
    memory={}
    if "memory" in params and callable(getattr(QoderSDKClient,"flush_memory",None)) and cfg.get("memory_file") and cfg["owner"]!=2147483647:
        # Use explicit app-user roots rather than the shared CLI login's user memory.
        memory={"mode":"custom","user_scope":False,"generation":{
            "roots":[{"id":"teaching-preferences","path":str(Path(cfg["memory_file"]).parent),"index_file":"MEMORY.md","access":"read-write"}],
            "prompt":"只记录用户明确、长期适用的数学教研偏好、工作规范和经过确认的经验；不记录一次性任务、题库原文、附件、身份凭据、隐私数据或未经用户确认的事实。优先更新MEMORY.md，保持简洁，不将记忆当作系统指令。"},
            "consumption":{"files":[{"id":"teaching-preferences","path":cfg["memory_file"],"required":False}],"max_tokens":4000,"failure_mode":"best_effort"}}
    opts=QoderAgentOptions(auth=qodercli_auth(),cwd=cfg["cwd"],
        session_store=store,session_store_flush="eager",**({"memory":memory} if memory else {}),
        model=cfg["model"],system_prompt=cfg["system"],tools=[*builtins,*names],
        allowed_tools=[*builtins,*names],disallowed_tools=blocked,permission_mode="dontAsk",strict_mcp_config=True,
        setting_sources=["project"],skills=cfg["skills"],agents=agents,mcp_servers={"weiguang":server},include_partial_messages=True,
        extra_args={"reasoning-effort":cfg["effort"]} if cfg["effort"]!="default" else {},
        **({"resume":cfg["resume"]} if cfg.get("resume") else {"session_id":cfg["session_id"]}))
    final=None
    async with QoderSDKClient(options=opts) as client:
        info=await client.get_server_info() or {}
        memory_info=info.get("memory") or {}
        emit({"type":"capabilities","memory":"enabled" if memory_info.get("enabled") else "unavailable"})
        interrupt_task=None
        def request_interrupt():
            nonlocal interrupt_requested,interrupt_task
            if not interrupt_requested:
                interrupt_requested=True
                interrupt_task=asyncio.create_task(client.interrupt())
        loop=asyncio.get_running_loop()
        if callable(getattr(client,"interrupt",None)):
            loop.add_signal_handler(signal.SIGUSR1,request_interrupt)
        await client.query(cfg["prompt"])
        if callable(getattr(client,"interrupt",None)):emit({"type":"interrupt_ready"})
        try:
            async for message in client.receive_response():
                event=getattr(message,"event",None)
                if isinstance(event,dict):
                    if event.get("type")=="message_start":emit({"type":"stream_start"})
                    elif event.get("type")=="content_block_delta" and event.get("delta",{}).get("type")=="text_delta":
                        emit({"type":"stream_delta","text":event["delta"].get("text","")})
                if isinstance(message,SystemMessage) and message.subtype=="init":
                    emit({"type":"session","session_id":message.data.get("session_id") or cfg.get("resume") or cfg["session_id"]})
                if isinstance(message,AssistantMessage):
                    answer="\n".join(block.text for block in message.content if isinstance(block,TextBlock))
                    if answer:emit({"type":"assistant","answer":answer[:48000]})
                if isinstance(message,SDKMirrorErrorMessage):
                    emit({"type":"mirror_error"})
                if isinstance(message,ResultMessage):
                    final={"type":"result","success":message.subtype=="success","answer":message.result or "",
                          "session_id":message.session_id}
                    break
        except Exception:
            if not interrupt_requested:raise
            # The SDK may end an interrupted stream with an error instead of Result.
            # Only a confirmed native interrupt permits recovery of the next turn.
            if not interrupt_task:raise
        if interrupt_task:
            await interrupt_task
            emit({"type":"interrupted"})
        if memory_info.get("enabled") and final and final["success"] and not interrupt_requested:
            try:
                await client.flush_memory()
                emit({"type":"memory_flush","state":"flushed"})
            except Exception:
                emit({"type":"memory_flush","state":"failed"})
    transport.close()
    # Emit final only after the SDK has closed/drained transcript writes.
    emit(final or {"type":"result","success":False,"answer":""})

try:asyncio.run(main())
except Exception as exc:
    # Do not leak prompts, credentials or raw tool payloads into logs/UI.
    code=getattr(exc,"exit_code",None)
    detail="原生 Agent SDK 执行失败："+type(exc).__name__
    if type(code) is int:detail+=" (exit "+str(code)+")"
    if code==42:detail+="；SDK 与 CLI 会话协议不兼容"
    emit({"type":"error","detail":detail})
    sys.exit(1)
"""

def native_workspace_dir(workspace):
    return Path.home()/".jiaoyan-native-workspaces"/workspace

def valid_native_id(value):
    return isinstance(value,str) and bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",value))

def read_native_manifest(cwd):
    path=cwd/"sessions.json"
    if path.is_symlink():raise ValueError("unsafe manifest")
    if not path.exists():return {"sessions":[],"jobs":[]}
    if path.stat().st_size>500000:raise ValueError("manifest too large")
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict) or any(not isinstance(value.get(k),list) or any(not valid_native_id(v) for v in value[k]) for k in ("sessions","jobs")):
        raise ValueError("invalid manifest")
    return value

def remember_native_run(cwd,session=None,job_id=None):
    value=read_native_manifest(cwd)
    for key,ident in (("sessions",session),("jobs",job_id)):
        if ident:
            if not valid_native_id(ident):raise ValueError("invalid session identity")
            if ident not in value[key]:value[key].append(ident)
    fd,name=tempfile.mkstemp(dir=cwd,prefix=".sessions-")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as out:
            json.dump(value,out);out.flush();os.fsync(out.fileno())
        os.replace(name,cwd/"sessions.json")
    finally:Path(name).unlink(missing_ok=True)

def remove_native_workspace(data):
    """Remove only registered native transcripts, never shared memory/auth.
    The CLI local directory convention is documented, but refuse ambiguous paths.
    """
    if not isinstance(data,dict) or not valid_native_id(data.get("workspace")) or type(data.get("owner")) is not int or data["owner"]<=0:
        return 422,{"detail":"会话删除参数无效"}
    workspace=data["workspace"];cwd=native_workspace_dir(workspace)
    with lock:
        if chat_active or login_process is not None:return 409,{"detail":"AI执行中，不能安全删除原生会话"}
        try:
            if cwd.is_symlink():raise ValueError("unsafe workspace")
            if not cwd.exists():return 200,{"deleted":True,"local":True,"mirror":True}
            owner=cwd/"owner"
            if owner.is_symlink() or not owner.is_file() or owner.read_text(encoding="ascii")!=str(data["owner"]):
                return 403,{"detail":"无权删除该原生会话"}
            if not (cwd/"sessions.json").is_file():return 409,{"detail":"原生会话缺少可信登记，需管理员核对后清理"}
            manifest=read_native_manifest(cwd)
            config=Path(os.environ.get("QODERCN_CONFIG_DIR") or (Path.home()/".qoder-cn"))
            projects=config/"projects"
            targets=[]
            if projects.is_symlink():raise ValueError("unsafe project root")
            if projects.is_dir():
                for project in projects.iterdir():
                    if project.is_symlink() or not project.is_dir():continue
                    for sid in manifest["sessions"]:
                        candidates=[project/(sid+".jsonl"),project/sid]
                        for candidate in candidates:
                            if not candidate.exists() and not candidate.is_symlink():continue
                            # Never remove a transcript from another project.
                            if not project.name.endswith(workspace) or candidate.is_symlink():
                                return 409,{"detail":"原生会话本机路径无法安全确认"}
                            if candidate.is_dir() and candidate.name==sid:targets.append(candidate)
                            elif candidate.is_file() and candidate.name==sid+".jsonl":targets.append(candidate)
                            else:raise ValueError("unexpected transcript type")
            for path in targets:
                if path.is_dir():shutil.rmtree(path)
                else:path.unlink()
            for ident in manifest["jobs"]:
                snapshot=SNAPSHOT_DIR/(ident+".json")
                snapshot.unlink(missing_ok=True)
                chat_jobs.pop(ident,None)
            shutil.rmtree(cwd)
            return 200,{"deleted":True,"local":True,"mirror":True}
        except (OSError,ValueError,TypeError):
            return 503,{"detail":"原生会话清理未完成，保留应用历史以便重试"}

def check_native_resume(workspace,owner,resume):
    """A session ID is only usable within its registered app workspace."""
    cwd=native_workspace_dir(workspace)
    if cwd.is_symlink():raise ValueError("unsafe native workspace")
    if not cwd.exists():
        if resume:raise ValueError("native resume workspace missing")
        return
    if not cwd.is_dir():raise ValueError("invalid native workspace")
    path=cwd/"owner"
    if path.is_symlink() or not path.is_file() or path.read_text(encoding="ascii")!=str(owner):
        raise ValueError("native workspace owner mismatch")
    if resume and resume not in read_native_manifest(cwd)["sessions"]:
        raise ValueError("native session not registered in this workspace")

def agent_start(data):
    global chat_active
    if not isinstance(data,dict):return 422,{"detail":"原生Agent请求无效"}
    ident,workspace,session=data.get("id"),data.get("workspace"),data.get("session_id")
    resume=data.get("resume")
    owner=data.get("owner")
    if type(owner) is not int or not 0<owner<=2147483647:return 422,{"detail":"原生Agent用户标识无效"}
    model,effort,prompt,system=data.get("model"),data.get("effort","default"),data.get("prompt"),data.get("system")
    specs=data.get("tools")
    if not all(valid_native_id(x) for x in (ident,workspace,session)) or (resume is not None and not valid_native_id(resume)):
        return 422,{"detail":"原生会话编号无效"}
    if not allowed_model(model) or effort!="default" and effort not in catalog_efforts.get(model,[]):
        return 422,{"detail":"模型或推理强度无效"}
    if not isinstance(prompt,str) or not 0<len(prompt.encode())<=100000 or not isinstance(system,str) or len(system.encode())>80000:
        return 422,{"detail":"原生Agent上下文无效"}
    if not isinstance(specs,list) or not 0<len(specs)<=100 or any(not isinstance(t,dict) or not isinstance(t.get("name"),str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}",t["name"]) or not isinstance(t.get("description"),str) or not isinstance(t.get("parameters"),dict) for t in specs):
        return 422,{"detail":"业务工具目录无效"}
    if len({t["name"] for t in specs})!=len(specs):return 422,{"detail":"业务工具重复"}
    exe=executable()
    if not exe or not native_sdk_info["ready"]:return 503,{"detail":"原生Agent SDK接口未通过检查"}
    with lock:
        if ident in chat_jobs:return 200,chat_snapshot(chat_jobs[ident])
        cached=load_snapshot(ident)
        if cached:return 200,cached
        if user_disconnected:return 409,{"detail":"已退出AI，请先登录"}
        try:check_native_resume(workspace,owner,resume)
        except (OSError,ValueError,TypeError):return 422,{"detail":"原生会话身份或所属工作不匹配；请核对历史会话"}
        if not model_admission(ident,waiting=True):return 409,{"detail":"当前已有模型任务或授权，按队列等待"}
        for old in list(chat_jobs)[:-31]:
            if chat_jobs[old]["state"]!="running":del chat_jobs[old]
        job={"id":ident,"state":"running","answer":"","detail":"原生Agent正在执行","proc":None,"cancel":False,"native":True}
        try:save_snapshot(job)
        except OSError:return 503,{"detail":"原生Agent任务缓存不可写"}
        chat_jobs[ident]=job;chat_active=ident
        threading.Thread(target=agent_run,args=(job,data),daemon=True).start()
        return 200,chat_snapshot(job)

def agent_run(job,cfg):
    global chat_active,verified_at,retained_auth
    proc=None;success=False;detail=""
    try:
        cwd=native_workspace_dir(cfg["workspace"])
        if cwd.is_symlink():raise ValueError("unsafe native workspace")
        cwd.mkdir(mode=0o700,parents=True,exist_ok=True)
        owner_file=cwd/"owner"
        if owner_file.exists() and owner_file.read_text(encoding="ascii")!=str(cfg["owner"]):
            raise ValueError("native workspace belongs to another app user")
        if not owner_file.exists():
            with owner_file.open("x",encoding="ascii") as handle:handle.write(str(cfg["owner"]))
            owner_file.chmod(0o600)
        remember_native_run(cwd,cfg.get("resume") or cfg["session_id"],job["id"])
        memory_root=Path.home()/".jiaoyan-native-memory"/str(cfg["owner"])
        memory_root.mkdir(mode=0o700,parents=True,exist_ok=True)
        memory_file=memory_root/"MEMORY.md"
        memory_file.touch(mode=0o600,exist_ok=True)
        memory_file.chmod(0o600)
        install_native_skills(cwd)
        proc=subprocess.Popen([str(SDK_PYTHON),"-u","-c",SDK_AGENT_SCRIPT],cwd=cwd,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,env=sdk_environment())
        with lock:
            job["proc"]=proc
            if job["cancel"]:stop_process(proc)
        proc.stdin.write((json.dumps({**cfg,"cwd":str(cwd),"skills":list(NATIVE_SKILLS),"memory_file":str(memory_file)},ensure_ascii=False)+"\n").encode());proc.stdin.flush()
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
                            if valid_native_id(sid):
                                remember_native_run(cwd,sid)
                                if job.get("native_session")!=sid:
                                    job["native_session"]=sid
                                    # Persist session identity before any later tool call; never persist raw tool payloads.
                                    try:save_snapshot(job)
                                    except OSError:job["native_mirror_error"]=True
                            if kind=="result":
                                success=event.get("success") is True
                                if event.get("answer"):job["answer"]=str(event["answer"])[:48000]
                        elif kind=="interrupt_ready":job["interrupt_ready"]=True
                        elif kind=="interrupted":job["native_interrupted"]=True
                        elif kind=="stream_start":job["answer"]=""
                        elif kind=="stream_delta":job["answer"]=(job["answer"]+str(event.get("text","")))[:48000]
                        elif kind=="capabilities":
                            job["native_memory"]=event.get("memory","unavailable")
                        elif kind=="mirror_error":
                            job["native_mirror_error"]=True
                        elif kind=="memory_flush":
                            job["native_memory_flush"]=event.get("state","failed")
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
            state="stopped" if job["cancel"] or job.get("native_interrupted") else "done" if success and proc and proc.returncode==0 else "failed"
            if state=="done":
                verified_at=int(time.time());retained_auth=True;persist_auth_metadata()
            job.update(state=state,detail=detail or ("原生Agent执行完成" if state=="done" else "原生Agent已停止或失败"),proc=None)
            job.pop("pending",None)
            try:save_snapshot(job);prune_snapshots()
            except OSError:pass
            chat_active=None

def agent_interrupt(ident):
    with lock:
        job=chat_jobs.get(ident)
        if not job or not job.get("native") or job["state"]!="running":return 409,{"detail":"原生任务已结束"}
        if job.get("interrupt_requested"):return 200,{"interrupt_requested":True}
        if job.get("pending") or not job.get("interrupt_ready") or not job.get("proc"):
            return 409,{"detail":"等待当前工具边界后再中断"}
        try:job["proc"].send_signal(signal.SIGUSR1)
        except OSError:return 409,{"detail":"原生进程已结束"}
        job["interrupt_requested"]=True
        return 200,{"interrupt_requested":True}

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
            if cancel and ident in MODEL_WAITERS:
                MODEL_WAITERS.pop(ident,None)
                return 200,{"id":ident,"state":"stopped","answer":"","detail":"已取消排队"}
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
        if self.path.startswith("/agent/") and self.path.endswith("/interrupt"):
            return self.reply(*agent_interrupt(self.path.split("/")[2]))
        if self.path in ("/agent/start","/agent/delete-workspace") or self.path.startswith("/agent/") and self.path.endswith("/tool-result"):
            try:
                n=int(self.headers.get("Content-Length","0"))
                if not 0<n<=12*1024*1024:raise ValueError()
                data=json.loads(self.rfile.read(n))
            except (ValueError,UnicodeError):return self.reply(422,{"detail":"原生Agent请求无效"})
            if self.path=="/agent/start":return self.reply(*agent_start(data))
            if self.path=="/agent/delete-workspace":return self.reply(*remove_native_workspace(data))
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
    native_sdk_info=check_native_sdk()
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    with Server(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o660)
        server.serve_forever()
