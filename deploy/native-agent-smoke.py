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

class WorkerError(RuntimeError):
    def __init__(self,status,detail):
        self.status=status
        super().__init__(str(status)+": "+detail)

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
            raise WorkerError(response.status,str(result.get("detail","request failed")))
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
    payload={"id":job,"workspace":workspace,"owner":OWNER,"session_id":job,"resume":resume,
        "model":model,"effort":"default","prompt":prompt,"system":"这是独立的合成SDK接口测试。按要求实际调用工具，准确返回结果。不要记住测试数据。","tools":specs}
    used=set();deadline=time.monotonic()+360
    try:
        # Reuse the same job ID when queued. Cancel it even if admission fails.
        while True:
            try:
                request("POST","/agent/start",payload)
                break
            except WorkerError as exc:
                if exc.status!=409 or "已有模型任务" not in str(exc) or time.monotonic()>=deadline:raise
                time.sleep(1)
        deadline=time.monotonic()+360
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
            request("POST","/chat/"+job+"/cancel",{})
        except Exception:pass

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--model",default="Auto")
    parser.add_argument("--vision",action="store_true",help="also test image content for the selected model")
    parser.add_argument("--recovery",action="store_true",help="also test native tool-error feedback and recovery")
    parser.add_argument("--cleanup",action="store_true",help="delete only this newly created synthetic workspace after success")
    args=parser.parse_args()
    status=request("GET","/status")
    if status.get("worker_version",0)<23 or not status.get("native_agent") or not status.get("chat_available") or status.get("busy") or status.get("waiting_count"):
        raise RuntimeError("Worker 23 / SDK required, and worker must be idle and authorized")
    print("PASS: Worker",status["worker_version"],"SDK preflight",flush=True)
    workspace=str(uuid4());nonce="WG-"+secrets.token_hex(6).upper()
    print("Synthetic smoke workspace:",workspace,flush=True)
    handlers={"smoke_token":("返回测试用随机验证码",lambda:text(nonce))}
    if args.vision:
        code=secrets.token_hex(3).upper()
        handlers["native_page"]=("返回包含六位验证码的合成原始图片",lambda:image(code))
    if args.recovery:
        attempts=[0]
        def retryable():
            attempts[0]+=1
            if attempts[0]==1:return {"is_error":True,"content":[{"type":"text","text":"合成测试：暂时无法读取，请重试此工具一次。"}]}
            return text(nonce)
        handlers["smoke_recover"]=("合成只读工具，首次暂时失败，重试后返回验证码",retryable)
    # Keep the same tool directory throughout this native session.
    first,used=run_turn(args.model,workspace,"调用 smoke_token 工具，原样输出验证码。",handlers)
    if "smoke_token" not in used or nonce not in first.get("answer",""):
        raise RuntimeError("actual MCP call/result not verified")
    print("PASS: actual MCP call",flush=True)
    resumed,used=run_turn(args.model,workspace,"上一轮工具给出的验证码是什么？不要调用工具，原样回答。",handlers,first["native_session"])
    if used or nonce not in resumed.get("answer",""):
        raise RuntimeError("native session resume not verified")
    print("PASS: native session resume",flush=True)
    print("Memory capability:",resumed.get("native_memory","unreported"),"flush:",resumed.get("native_memory_flush","unreported"),flush=True)
    sid=resumed["native_session"]
    if args.vision:
        result,used=run_turn(args.model,workspace,"调用 native_page，读取图中六位验证码，原样回答。",handlers,sid)
        if "native_page" not in used or code not in result.get("answer",""):
            raise RuntimeError("actual visual MCP image result not verified")
        sid=result["native_session"]
        print("PASS: actual visual MCP image",flush=True)
    if args.recovery:
        result,used=run_turn(args.model,workspace,"调用 smoke_recover，若暂时失败，按工具提示重试，输出成功返回的验证码。",handlers,sid)
        if "smoke_recover" not in used or attempts[0]<2 or nonce not in result.get("answer",""):
            raise RuntimeError("native tool error recovery not verified")
        print("PASS: actual tool error feedback and recovery",flush=True)
    if args.cleanup:
        result=request("POST","/agent/delete-workspace",{"workspace":workspace,"owner":OWNER})
        if not result.get("deleted"):raise RuntimeError("synthetic workspace deletion not confirmed")
        print("PASS: synthetic workspace cleanup endpoint",flush=True)
    print("NATIVE_SMOKE_PASSED (synthetic SDK checks only; business/video acceptance still required)",flush=True)

if __name__=="__main__":main()
