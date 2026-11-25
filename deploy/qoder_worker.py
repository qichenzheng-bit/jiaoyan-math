#!/usr/bin/env python3
"""Unix-socket-only Qoder CN worker. Separate non-root service account."""
import errno
import json
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

def model_catalog():
    with lock:
        names = list(FALLBACK_MODELS if catalog is None else catalog)
        return {"models": [{"id": n, "label": n, "efforts": ["default"]} for n in names],
                "source": "fallback" if catalog is None else "cli",
                "updated_at": catalog_at}

def refresh_models():
    global catalog, catalog_at
    with lock:
        if login_process is not None or chat_active:
            return 409, {"detail": "请先完成当前授权或对话"}
    exe = executable()
    if not exe:
        return 503, {"detail": "未安装 Qoder CN CLI"}
    try:
        with tempfile.TemporaryDirectory(prefix="qoder-models-") as work:
            proc = subprocess.Popen([exe, "--list-models"], cwd=work, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                out, err = proc.communicate(timeout=35)
            except subprocess.TimeoutExpired:
                stop_process(proc)
                proc.communicate()
                return 504, {"detail": "模型清单读取超时，保留此前清单"}
        output = out.decode("utf-8", "replace")
        no_models = "no models available" in (output + err.decode("utf-8", "replace")).lower()
        if proc.returncode != 0 and not no_models:
            return 503, {"detail": "CLI 模型探测失败，保留此前清单"}
        names = [] if no_models else parse_models(output)
        if not names and not no_models:
            return 503, {"detail": "无法解析 CLI 模型清单，保留此前清单"}
        with lock:
            catalog, catalog_at = names, int(time.time())
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
    global login_process
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
                login_process = None

def start_login():
    global login_process, verified_at, catalog, catalog_at
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
        verified_at = None
        catalog, catalog_at = None, None
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
                "verified_at": verified_at, "login": dict(login), "auth_ui": True, "model_discovery": True, "worker_version": 6, "video_inference": True, "busy": bool(chat_active or login_process is not None), "chat_available": available, "durable_results": True}

def invoke(model, prompt):
    global verified_at
    with lock:
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
                with lock:
                    verified_at = None
                return 503, {"detail": "CLI 调用失败，请检查登录状态及网络"}
            answer = out.decode("utf-8", errors="replace").strip()
            if not answer:
                return 503, {"detail": "CLI 未返回正文"}
            with lock:
                verified_at = int(time.time())
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

def chat_snapshot(job):
    return {k: job[k] for k in ("id","state","answer","detail")}


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

def chat_run(job, exe, model, prompt):
    video = job.get("video", False)
    output_limit = 300000 if video else 48000
    global chat_active
    proc = None
    failure = False
    try:
        with tempfile.TemporaryDirectory(prefix="qoder-chat-") as cwd:
            # Prompt is passed as one argv entry; bounded by API and worker.
            args = [exe,"-m",model,"--tools","","--no-session-persistence","--output-format","stream-json"]
            if video:
                if job["system"]: args += ["--system-prompt", job["system"]]
                if job["effort"] != "default": args += ["--reasoning-effort",job["effort"]]
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
            job.update(state=state,detail={"stopped":"已停止生成","failed":"模型调用失败或超时，请检查授权、额度及 CLI 事件格式","done":""}[state],proc=None)
            try:
                save_snapshot(job)
                prune_snapshots()
            except OSError:
                # Live result remains available if the disk is temporarily unavailable.
                pass
            chat_active=None

def chat_start(data, video=False):
    global chat_active
    if not isinstance(data,dict): return 422,{"detail":"请求无效"}
    ident,model,prompt=data.get("id"),data.get("model"),data.get("prompt")
    if not isinstance(ident,str) or not JOB_ID.fullmatch(ident) or not allowed_model(model) or not isinstance(prompt,str) or "\x00" in prompt or not 0<len(prompt.encode("utf-8"))<=(120000 if video else 100000):
        return 422,{"detail":"模型或上下文无效；请检查模型及提示词长度"}
    system,effort,timeout=data.get("system",""),data.get("effort","default"),data.get("timeout",900)
    if video and (not isinstance(system,str) or "\x00" in system or len(system.encode("utf-8"))>4096 or effort not in ("default","low","medium","high","xhigh","max") or type(timeout) is not int or not 1<=timeout<=900):
        return 422,{"detail":"视频模型参数无效"}
    exe=executable()
    if not exe: return 503,{"detail":"未安装 Qoder CN CLI"}
    with lock:
        if ident in chat_jobs: return 200,chat_snapshot(chat_jobs[ident])
        cached=load_snapshot(ident)
        if cached: return 200,cached
        if chat_active or login_process is not None: return 409,{"detail":"当前已有模型任务或授权，请先完成"}
        # Keep a bounded number of completed jobs for reconnecting clients.
        for old in list(chat_jobs)[:-31]:
            if chat_jobs[old]["state"]!="running": del chat_jobs[old]
        job={"id":ident,"state":"running","answer":"","detail":"","proc":None,"cancel":False,"video":video,"system":system,"effort":effort,"timeout":timeout}
        try: save_snapshot(job)
        except OSError: return 503,{"detail":"任务结果缓存不可写，请检查执行服务存储"}
        chat_jobs[ident]=job
        chat_active=ident
        threading.Thread(target=chat_run,args=(job,exe,model,prompt),daemon=True).start()
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
        return 200,chat_snapshot(job)

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
        return self.reply(404, {"detail": "Not found"})
    def do_POST(self):
        if self.path.startswith("/chat/") and self.path.endswith("/cancel"):
            return self.reply(*chat_state(self.path.split("/")[2], True))
        if self.path in ("/chat/start", "/video/start"):
            try:
                n=int(self.headers.get("Content-Length","0"))
                if not 0<n<=(800000 if self.path == "/video/start" else 200000): raise ValueError()
                data=json.loads(self.rfile.read(n))
            except (ValueError,UnicodeError): return self.reply(422,{"detail":"请求无效"})
            return self.reply(*chat_start(data, video=self.path == "/video/start"))
        if self.path == "/models/refresh":
            return self.reply(*refresh_models())
        if self.path == "/login/start":
            return self.reply(*start_login())
        if self.path == "/login/cancel":
            return self.reply(200, cancel_login())
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
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    with Server(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o660)
        server.serve_forever()
