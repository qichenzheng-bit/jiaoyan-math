#!/usr/bin/env python3
"""Opt-in real Qoder SDK smoke test through the isolated Unix-socket worker.

Uses synthetic data only. Does not modify the business database or change login.
Run using the deployed backend venv, under the authorized application account.
"""
import argparse
import base64
import http.client
import io
import json
import secrets
import socket
import time
from uuid import uuid4

SOCKET="/run/jiaoyan-qoder/worker.sock"
OWNER=2147483647  # reserved synthetic smoke-test scope, never an application user

class Connection(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)

def request(method,path,data=None):
    conn=Connection("localhost",timeout=45)
    try:
        conn.request(method,path,json.dumps(data).encode() if data is not None else None,{"Content-Type":"application/json"})
        response=conn.getresponse()
        result=json.loads(response.read(2_500_000))
        if response.status!=200:
            raise RuntimeError(str(response.status)+": "+str(result.get("detail","request failed")))
        return result
    finally:conn.close()

def text(value):
    return {"content":[{"type":"text","text":value}]}

def image(code):
    from PIL import Image, ImageDraw, ImageFont
    im=Image.new("RGB",(800,300),"white")
    draw=ImageDraw.Draw(im)
    font=ImageFont.load_default(size=64)
    draw.text((80,80),code,font=font,fill="black")
    buffer=io.BytesIO();im.save(buffer,format="PNG")
    return {"content":[{"type":"image","mimeType":"image/png","data":base64.b64encode(buffer.getvalue()).decode()}]}

def run_turn(model,workspace,prompt,handlers,resume=None):
    job=str(uuid4())
    schema={"type":"object","properties":{},"additionalProperties":False}
    specs=[{"name":name,"description":desc,"parameters":schema,"write":False} for name,(desc,_) in handlers.items()]
    request("POST","/agent/start",{"id":job,"workspace":workspace,"owner":OWNER,"session_id":job,"resume":resume,
        "model":model,"effort":"default","prompt":prompt,"system":"这是独立的合成SDK接口测试。按要求实际调用工具，准确返回结果。不要记住测试数据。","tools":specs})
    used=set();deadline=time.monotonic()+360
    try:
        while time.monotonic()<deadline:
            reply=request("GET","/chat/"+job)
            if reply["state"]!="running":
                if reply["state"]!="done":raise RuntimeError(reply.get("detail","native SDK failed"))
                if reply.get("native_mirror_error"):raise RuntimeError("session mirror write failed")
                if not reply.get("native_session"):raise RuntimeError("native session ID missing")
                return reply,used
            call=reply.get("pending_tool")
            if call:
                name=call["name"]
                if name not in handlers or call["args"]:raise RuntimeError("unexpected tool invocation")
                request("POST","/agent/"+job+"/tool-result",{"id":call["id"],"result":handlers[name][1]()})
                used.add(name)
            time.sleep(.5)
        raise RuntimeError("native smoke timeout")
    finally:
        try:
            if request("GET","/chat/"+job)["state"]=="running":request("POST","/chat/"+job+"/cancel",{})
        except Exception:pass

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--model",default="Auto")
    parser.add_argument("--vision",action="store_true",help="also test image content for the selected model")
    args=parser.parse_args()
    status=request("GET","/status")
    if status.get("worker_version",0)<16 or not status.get("native_agent") or status.get("busy"):
        raise RuntimeError("Worker 16 / SDK required, and worker must be idle")
    workspace=str(uuid4());nonce="WG-"+secrets.token_hex(6).upper()
    handlers={"smoke_token":("返回测试用随机验证码",lambda:text(nonce))}
    first,used=run_turn(args.model,workspace,"调用 smoke_token 工具，原样输出验证码。",handlers)
    assert "smoke_token" in used and nonce in first.get("answer",""),"actual MCP call/result not verified"
    resumed,used=run_turn(args.model,workspace,"上一轮工具给出的验证码是什么？不要调用工具，原样回答。",handlers,first["native_session"])
    assert not used and nonce in resumed.get("answer",""),"native session resume not verified"
    print("PASS: actual MCP call and native session resume")
    print("Memory capability:",resumed.get("native_memory","unreported"),"flush:",resumed.get("native_memory_flush","unreported"))
    if args.vision:
        code=secrets.token_hex(3).upper()
        visual={"smoke_image":("返回包含六位验证码的合成图片",lambda:image(code))}
        result,used=run_turn(args.model,workspace,"调用 smoke_image，读取图中六位验证码，原样回答。",visual,resumed["native_session"])
        assert "smoke_image" in used and code in result.get("answer",""),"actual visual MCP result not verified"
        print("PASS: actual visual MCP image")
    print("Synthetic smoke workspace:",workspace)

if __name__=="__main__":main()
