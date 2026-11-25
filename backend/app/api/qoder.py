"""Only talks to a separately provisioned, unprivileged local worker."""
import http.client
import json
import socket
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models import Setting, User
from app.core.security import audit
from app.core.security import current_user, require_origin

router = APIRouter(prefix="/qoder",tags=["qoder"],dependencies=[Depends(current_user)])
SOCKET = "/run/jiaoyan-qoder/worker.sock"
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

MODEL_KEY = "ai.qoder.model"
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

@router.post("/models/refresh",dependencies=[Depends(require_origin)])
def models_refresh():
    return request("POST","/models/refresh",{})

class ModelPreference(BaseModel):
    model: str=Field(min_length=1,max_length=80,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")

@router.get("/preferences")
def model_preference(db:Session=Depends(get_db)):
    row=db.get(Setting,MODEL_KEY)
    return {"model":row.value if row else "Auto"}

@router.put("/preferences",dependencies=[Depends(require_origin)])
def set_model(body:ModelPreference,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if body.model not in {m["id"] for m in available_models()["models"]}:
        raise HTTPException(422,"该模型不在当前可用清单中")
    db.merge(Setting(key=MODEL_KEY,value=body.model))
    audit(db,"qoder.model.update",user.id)
    db.commit()
    return body.model_dump()
