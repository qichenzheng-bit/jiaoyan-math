"""Only talks to a separately provisioned, unprivileged local worker."""
import http.client
import json
import socket
import asyncio
import logging
import threading
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models import Setting, User
from app.core.security import audit
from app.core.security import current_user, require_origin

router = APIRouter(prefix="/qoder",tags=["qoder"],dependencies=[Depends(current_user)])
SOCKET = "/run/jiaoyan-qoder/worker.sock"
MODEL_REFRESH_INTERVAL = 24 * 3600
MODEL_REFRESH_CHECK = 300
model_refresh_lock = threading.Lock()
last_refresh_success = 0.0
logger = logging.getLogger(__name__)
class LocalConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)

def request(method,path,body=None):
    connection=LocalConnection("localhost",timeout=3 if method=="GET" else 48)
    try:
        connection.request(method,path,json.dumps(body,ensure_ascii=False).encode() if body is not None else None,{"Content-Type":"application/json"})
        response=connection.getresponse()
        result=json.loads(response.read(524288))
        if response.status!=200:
            raise HTTPException(response.status if response.status in (404,409,422,503,504) else 502, result.get("detail","Qoder调用失败"))
        return result
    except (OSError,ValueError,http.client.HTTPException):
        raise HTTPException(503,"Qoder CN 执行服务尚未就绪，请先在服务器安装并授权")
    finally:
        connection.close()

class Prompt(BaseModel):
    model: str=Field(default="Auto",min_length=1,max_length=80,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
    prompt: str=Field(min_length=1,max_length=12000)

@router.get("/status")
def status():
    try: return request("GET","/status")
    except HTTPException: return {"available":False,"detail":"执行服务未连接"}

@router.post("/test",dependencies=[Depends(require_origin)])
def test(body:Prompt):
    if not body.prompt.strip(): raise HTTPException(422,"请输入测试内容")
    return request("POST","/test",body.model_dump())

@router.post("/login/start", dependencies=[Depends(require_origin)])
def login_start():
    return request("POST", "/login/start", {})

@router.post("/login/cancel", dependencies=[Depends(require_origin)])
def login_cancel():
    return request("POST", "/login/cancel", {})

@router.post("/login/disconnect", dependencies=[Depends(require_origin)])
def login_disconnect():
    return request("POST", "/login/disconnect", {})

MODEL_KEY = "ai.qoder.model"
VIDEO_MODEL_KEY = "ai.qoder.video_model"
EFFORT_KEY = "ai.qoder.effort"
VIDEO_EFFORT_KEY = "ai.qoder.video_effort"
VIDEO_EFFORTS = {"low","medium","high","xhigh","max"}
def fallback():
    return {"models":[{"id":m,"label":m,"efforts":["default"]} for m in ("Auto","Fast")],"source":"fallback","updated_at":None}

def available_models():
    try:
        return request("GET","/models")
    except HTTPException as exc:
        if exc.status_code in (404,503):
            return fallback()
        raise

@router.get("/models")
def models():
    return available_models()

def _refresh_catalog():
    """Caller holds model_refresh_lock; worker remains the source of truth."""
    global last_refresh_success
    result = request("POST", "/models/refresh", {})
    if result.get("source") != "cli" or not isinstance(result.get("models"), list):
        raise HTTPException(503, "未取得 CLI 实际模型清单")
    last_refresh_success = time.monotonic()
    return result

def refresh_if_due(now=None):
    """Refresh on startup or once the worker's actual catalog is 24 hours old."""
    if not model_refresh_lock.acquire(blocking=False):
        return "busy"
    try:
        status = request("GET", "/status")
        if status.get("user_disconnected") or not status.get("available") or not status.get("model_discovery"):
            return "unavailable"
        if status.get("busy") or (status.get("login") or {}).get("state") in ("starting", "waiting"):
            return "busy"
        catalog = request("GET", "/models")
        updated = catalog.get("updated_at")
        current = time.time() if now is None else now
        if catalog.get("source") == "cli" and isinstance(updated, (int, float)) and 0 <= current - updated < MODEL_REFRESH_INTERVAL:
            return "fresh"
        _refresh_catalog()
        return "updated"
    except HTTPException as exc:
        # Do not log account data or raw CLI output. Retry at the next check.
        logger.info("Qoder scheduled catalog refresh deferred (HTTP %s)", exc.status_code)
        return "retry"
    finally:
        model_refresh_lock.release()

async def model_refresh_loop():
    # Delay the first check slightly so application startup is never blocked.
    await asyncio.sleep(10)
    while True:
        try:
            await asyncio.to_thread(refresh_if_due)
        except Exception:
            logger.warning("Qoder scheduled catalog refresh failed")
        await asyncio.sleep(MODEL_REFRESH_CHECK)

@router.post("/models/refresh",dependencies=[Depends(require_origin)])
def models_refresh():
    requested = time.monotonic()
    with model_refresh_lock:
        # Coalesce a manual refresh with a successful overlapping scheduled one.
        if last_refresh_success >= requested:
            result = request("GET", "/models")
            if result.get("source") == "cli":
                return result
        return _refresh_catalog()

class ModelPreference(BaseModel):
    model: str=Field(min_length=1,max_length=80,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
    video_model: str|None=Field(default=None,min_length=1,max_length=80,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
    effort: str|None=Field(default=None,max_length=16)
    video_effort: str|None=Field(default=None,max_length=16)

def stored_effort(db,key):
    row=db.get(Setting,key)
    return row.value if row else "default"

def validate_effort(catalog,model,effort,video=False):
    if effort=="default":return
    if video and effort not in VIDEO_EFFORTS:raise HTTPException(422,"视频引擎不支持该档位")
    if catalog.get("source")!="cli" or not any(m.get("id")==model and effort in m.get("efforts",[]) for m in catalog.get("models",[])):
        raise HTTPException(422,"该模型未报告所选推理强度，请刷新模型")

def assistant_effort(db,model,override=None):
    prefs=model_preference(db)
    effort=override if override is not None else (prefs["effort"] if prefs["model"]==model else "default")
    if effort!="default":validate_effort(available_models(),model,effort)
    return {"effort":effort} if effort!="default" else {}

def video_model_preference(db):
    row=db.get(Setting,VIDEO_MODEL_KEY)
    return row.value if row else "Auto"

@router.get("/preferences")
def model_preference(db:Session=Depends(get_db)):
    row=db.get(Setting,MODEL_KEY)
    return {"model":row.value if row else "Auto","video_model":video_model_preference(db),"effort":stored_effort(db,EFFORT_KEY),"video_effort":stored_effort(db,VIDEO_EFFORT_KEY)}

@router.put("/preferences",dependencies=[Depends(require_origin)])
def set_model(body:ModelPreference,db:Session=Depends(get_db),user:User=Depends(current_user)):
    catalog=available_models()
    options={m["id"] for m in catalog["models"]}
    old=model_preference(db)
    video_model=body.video_model or old["video_model"]
    effort=body.effort if body.effort is not None else (old["effort"] if old["model"]==body.model else "default")
    video_effort=body.video_effort if body.video_effort is not None else (old["video_effort"] if old["video_model"]==video_model else "default")
    validate_effort(catalog,body.model,effort)
    validate_effort(catalog,video_model,video_effort,True)
    db.merge(Setting(key=EFFORT_KEY,value=effort))
    db.merge(Setting(key=VIDEO_EFFORT_KEY,value=video_effort))
    if body.model not in options or (body.video_model is not None and body.video_model not in options):
        raise HTTPException(422,"该模型不在当前可用清单中")
    db.merge(Setting(key=MODEL_KEY,value=body.model))
    if body.video_model is not None:
        db.merge(Setting(key=VIDEO_MODEL_KEY,value=body.video_model))
    audit(db,"qoder.model.update",user.id)
    db.commit()
    return model_preference(db)
