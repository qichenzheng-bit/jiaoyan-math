"""Private Unix-socket adapter for the pinned upstream video runtime.
The original Qoder account, CLI and concurrency guard remain owned by jiaoyan-qoder.
"""
import http.client
import json
import math
import socket
import time
from uuid import uuid4

SOCKET = "/run/jiaoyan-qoder/worker.sock"
MAX_RESPONSE = 2_000_000


class LocalConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)


def request(method, path, data=None):
    conn = LocalConnection("localhost", timeout=8)
    try:
        body = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        conn.request(method, path, body, {"Content-Type": "application/json"})
        response = conn.getresponse()
        raw = response.read(MAX_RESPONSE+1)
        if len(raw) > MAX_RESPONSE:
            raise RuntimeError("QODER_VIDEO_RESPONSE_TOO_LARGE")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("QODER_VIDEO_INVALID_RESPONSE")
        return response.status, payload
    finally:
        conn.close()


def target(kind):
    if kind != "qoder_cli":
        return {"installed": False, "path": ""}
    try:
        code, data = request("GET", "/status")
        available = code == 200 and data.get("available") and data.get("video_inference")
    except (OSError, ValueError, http.client.HTTPException, RuntimeError):
        available = False
    return {"installed": bool(available), "path": "jiaoyan-qoder-socket" if available else ""}


def cancelled(chat_id):
    from weiguang_backend.ai.cli_probe import is_chat_cancelled
    from weiguang_backend.services.task_control import active_job, is_cancel_requested
    job = active_job()
    return bool(is_cancel_requested(job) if job else (chat_id and is_chat_cancelled(chat_id)))


def chat_cli_stream(kind, exe, model, effort="default", speed="default", prompt="",
                    images=None, chat_id="", timeout=900, resume="", max_reply=0,
                    system_prompt_file="", **kwargs):
    started = time.monotonic()
    ident = str(uuid4())
    accepted = False
    terminal = False
    def done(status, **extra):
        return {"type":"done","status":status,"latency_ms":int((time.monotonic()-started)*1000),**extra}
    try:
        if kind != "qoder_cli" or speed != "default" or images or resume:
            raise RuntimeError("QODER_VIDEO_UNSUPPORTED_OPTIONS")
        if not prompt or "\x00" in prompt or len(prompt.encode("utf-8")) > 120000:
            raise RuntimeError("QODER_VIDEO_PROMPT_TOO_LONG_OR_EMPTY")
        duration = max(1, min(900, math.ceil(timeout or 900)))
        deadline = started + duration
        while True:
            if cancelled(chat_id):
                yield done("cancelled", error="JOB_CANCELLED_BEFORE_CLI_START")
                return
            remaining = int(deadline-time.monotonic())
            if remaining < 1:
                raise RuntimeError("QODER_VIDEO_QUEUE_TIMEOUT")
            code, data = request("POST","/video/start",{
                "id":ident,"model":model,"prompt":prompt,"system":system_prompt_file,
                "effort":effort,"timeout":remaining})
            if code != 409:
                break
            time.sleep(1)
        if code != 200:
            raise RuntimeError("QODER_VIDEO_REQUEST_REJECTED_"+str(code))
        accepted = True
        prior = ""
        while True:
            if cancelled(chat_id):
                yield done("cancelled", error="JOB_CANCELLED")
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("QODER_VIDEO_TIMEOUT")
            state = data.get("state")
            answer = data.get("answer")
            if not isinstance(answer, str):
                raise RuntimeError("QODER_VIDEO_INVALID_RESPONSE")
            if state == "done":
                terminal = True
                if not answer.strip():
                    raise RuntimeError("CLI_RESPONSE_EMPTY")
                yield done("ok",text=answer)
                return
            if state in ("failed","stopped"):
                terminal = True
                raise RuntimeError("QODER_VIDEO_WORKER_"+state.upper())
            if state != "running":
                raise RuntimeError("QODER_VIDEO_UNKNOWN_STATE")
            if answer.startswith(prior) and len(answer)>len(prior):
                yield {"type":"text","text":answer[len(prior):]}
            prior = answer
            time.sleep(0.8)
            code,data=request("GET","/chat/"+ident)
            if code != 200:
                raise RuntimeError("QODER_VIDEO_STATUS_UNAVAILABLE")
    except (OSError, ValueError, http.client.HTTPException, RuntimeError) as exc:
        error=str(exc) if isinstance(exc,RuntimeError) else "QODER_VIDEO_TRANSPORT_ERROR"
        yield done("failed",error=error)
    finally:
        if accepted and not terminal:
            try:
                request("POST","/chat/"+ident+"/cancel",{})
            except (OSError, ValueError, http.client.HTTPException, RuntimeError):
                pass


def chat_cli(*args, **kwargs):
    for event in chat_cli_stream(*args, **kwargs):
        if event.get("type")=="done":
            return event
    return {"status":"failed","error":"QODER_VIDEO_NO_RESULT"}


def create_app():
    from weiguang_backend.ai import cli_login, cli_probe, model_selection, model_runtime
    cli_login.chat_target = target
    cli_probe.chat_cli = chat_cli
    cli_probe.chat_cli_stream = chat_cli_stream
    model_selection.CLI_PROTOCOLS = ("qoder_cli",)
    model_runtime.CLI_PROTOCOLS = ("qoder_cli",)
    from weiguang_backend.main import create_app as upstream
    from weiguang_backend.core.models import AiProvider, GlobalAiSetting
    app = upstream()
    with app.state.SessionLocal() as db:
        provider = db.query(AiProvider).filter_by(protocol="qoder_cli",deleted_at=None).first()
        if provider is None:
            provider=AiProvider(name="Qoder CN",preset="qoder_cli",protocol="qoder_cli",
                base_url="local-cli://qoder_cli",encrypted_key="",json_mode=False)
            db.add(provider)
            db.flush()
        for group in ("other","edit"):
            setting=db.get(GlobalAiSetting,group)
            if setting is None:
                db.add(GlobalAiSetting(id=group,provider_id=provider.id,model_id="Auto",
                    reasoning_effort="default",speed="default",timeout_seconds=900))
            elif setting.provider_id != provider.id:
                setting.provider_id=provider.id
                setting.model_id="Auto"
                setting.reasoning_effort="default"
                setting.speed="default"
                setting.timeout_seconds=900
        db.commit()
    return app
