"""Private Unix-socket adapter for the pinned upstream video runtime.
The original Qoder account, CLI and concurrency guard remain owned by jiaoyan-qoder.
"""
import http.client
import json
import math
import socket
import time
import os
import hmac
from threading import Event
from contextvars import ContextVar
from uuid import uuid4

SOCKET = "/run/jiaoyan-qoder/worker.sock"
MAX_RESPONSE = 2_000_000
PROMPT_LIMIT = 32000
_job_prompt = ContextVar('job_prompt', default=None)
_session_factory = None
_factory_ready=Event()
_initializing=False


def job_supplement():
    if _initializing and not _factory_ready.wait(30):
        raise RuntimeError('VIDEO_PROMPT_STORE_NOT_READY')
    if _session_factory is None:return ''
    from sqlalchemy import select
    from weiguang_backend.services.task_control import active_job
    from weiguang_backend.core.models import ClientSetting
    ident=active_job()
    if not ident:return ''
    with _session_factory() as db:
        row=db.scalar(select(ClientSetting).where(ClientSetting.key=='jiaoyan:video:prompt:'+ident,ClientSetting.account_id==''))
        if row is None:return ''
        value=json.loads(row.value)
        text=value.get('text','') if isinstance(value,dict) else ''
        if not isinstance(text,str) or '\x00' in text or len(text.encode())>PROMPT_LIMIT:
            raise RuntimeError('VIDEO_PROMPT_SNAPSHOT_INVALID')
        return text


def append_supplement(prompt,text):
    if not text:return prompt
    return prompt+'\n\n【用户教学补充要求；固定教学规范、题源数学条件、渲染校验及安全限制优先】\n'+text+'\n【补充结束】'


def capture_job_add(original):
    def wrapped(db,lesson,kind,*args,**kwargs):
        snapshot=_job_prompt.get()
        if snapshot is None or kind!='generate':return original(db,lesson,kind,*args,**kwargs)
        from weiguang_backend.core.models import ClientSetting
        commit=kwargs.pop('commit',True)
        job=original(db,lesson,kind,*args,commit=False,**kwargs)
        db.add(ClientSetting(key='jiaoyan:video:prompt:'+job.id,account_id='',value=json.dumps(snapshot,ensure_ascii=False)))
        if commit:
            db.commit();db.refresh(job)
        return job
    return wrapped



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
        prompt=append_supplement(prompt,job_supplement())
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


def add_prompt_routes(router):
    from fastapi import HTTPException, Request
    from pydantic import BaseModel, ConfigDict, Field
    original=next((r.endpoint for r in router.routes if getattr(r,'path',None)=='/lessons/{id}/generate' and 'POST' in getattr(r,'methods',set())),None)
    if original is None:raise RuntimeError('VIDEO_GENERATION_ROUTE_MISSING')

    class Supplement(BaseModel):
        model_config=ConfigDict(extra='forbid')
        text:str=Field(default='',max_length=16000)
        revision:int=Field(ge=0)

    def authorize(request:Request):
        expected=os.environ.get('WEIGUANG_API_TOKEN','')
        if not expected or not hmac.compare_digest(request.headers.get('X-API-Key','').encode(),expected.encode()):
            raise HTTPException(403,'VIDEO_ENGINE_TOKEN_REQUIRED')

    @router.get('/jiaoyan/prompt-capability')
    def prompt_capability(request:Request):
        authorize(request)
        return {'supported':True,'max_bytes':PROMPT_LIMIT,'snapshot':'job'}

    @router.post('/jiaoyan/lessons/{id}/generate',status_code=202)
    def generate_with_supplement(id:str,body:Supplement,request:Request):
        authorize(request)
        if '\x00' in body.text or len(body.text.encode())>PROMPT_LIMIT:
            raise HTTPException(422,'VIDEO_PROMPT_TOO_LONG')
        token=_job_prompt.set(body.model_dump())
        try:return original(id)
        finally:_job_prompt.reset(token)
    return router


def create_app():
    global _session_factory,_initializing
    from weiguang_backend.api import routers
    from weiguang_backend.api.routers import production
    production.job_add=capture_job_add(production.job_add)
    original_builder=routers.build_production_router
    def build_with_prompt_routes(ctx,exports):
        return add_prompt_routes(original_builder(ctx,exports))
    routers.build_production_router=build_with_prompt_routes
    from weiguang_backend.ai import cli_login, cli_probe, model_selection, model_runtime
    cli_login.chat_target = target
    cli_probe.chat_cli = chat_cli
    cli_probe.chat_cli_stream = chat_cli_stream
    model_selection.CLI_PROTOCOLS = ("qoder_cli",)
    model_runtime.CLI_PROTOCOLS = ("qoder_cli",)
    from weiguang_backend.main import create_app as upstream
    from weiguang_backend.core.models import AiProvider, GlobalAiSetting
    _initializing=True
    _factory_ready.clear()
    try:
        app=upstream()
        _session_factory=app.state.SessionLocal
    finally:
        _initializing=False
        _factory_ready.set()
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
