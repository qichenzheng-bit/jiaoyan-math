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
AUTH_DOMAINS = ("qoder.com.cn", "qoder.com", "aliyun.com", "alibabacloud.com")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
URL = re.compile(r"https://[^\s<>\x00-\x20\"']+")

def executable():
    found = shutil.which("qoderclicn")
    if found:
        return found
    home = Path.home()
    for path in (home / ".qoder-cn/bin/qoderclicn/qoderclicn", home / ".qoder-cn/bin/qoderclicn", home / ".local/bin/qoderclicn"):
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
        name = text.lstrip("- *").strip()
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
        if login_process is not None:
            return 409, {"detail": "请先完成或取消授权"}
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
                "verified_at": verified_at, "login": dict(login), "auth_ui": True, "model_discovery": True, "worker_version": 2}

def invoke(model, prompt):
    global verified_at
    with lock:
        if login_process is not None:
            return 409, {"detail": "请先完成或取消正在进行的授权"}
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
        if self.path == "/models":
            return self.reply(200, model_catalog())
        return self.reply(404, {"detail": "Not found"})
    def do_POST(self):
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
