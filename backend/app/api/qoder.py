"""Only talks to a separately provisioned, unprivileged local worker."""
import http.client
import json
import socket
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from app.core.security import current_user, require_origin

router = APIRouter(prefix="/qoder",tags=["qoder"],dependencies=[Depends(current_user)])
SOCKET = "/run/jiaoyan-qoder/worker.sock"
class LocalConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)

def request(method,path,body=None):
    connection=LocalConnection("localhost",timeout=48)
    try:
        connection.request(method,path,json.dumps(body,ensure_ascii=False).encode() if body is not None else None,{"Content-Type":"application/json"})
        response=connection.getresponse()
        result=json.loads(response.read(262144))
        if response.status!=200:
            raise HTTPException(response.status if response.status in (409,422,503,504) else 502, result.get("detail","Qoder调用失败"))
        return result
    except (OSError,ValueError,http.client.HTTPException):
        raise HTTPException(503,"Qoder CN 执行服务尚未就绪，请先在服务器安装并授权")
    finally:
        connection.close()

class Prompt(BaseModel):
    model: Literal["Auto","Fast"]="Auto"
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
