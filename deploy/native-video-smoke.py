#!/usr/bin/env python3
"""Synthetic native video inference check, never executes generated code."""
import argparse
import ast
import importlib.util
import time
from pathlib import Path
from uuid import uuid4

def load_client():
    spec=importlib.util.spec_from_file_location("native_smoke_client",Path(__file__).with_name("native-agent-smoke.py"))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def validate_code(answer):
    text=answer.strip()
    fence=chr(96)*3
    if text.startswith(fence) and text.endswith(fence):
        text=text.split("\n",1)[1][:-3].strip()
    tree=ast.parse(text)
    scenes=[x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=="SmokeScene"]
    if len(scenes)!=1 or not any(isinstance(x,ast.FunctionDef) and x.name=="construct" for x in scenes[0].body):
        raise ValueError("synthetic Manim code contract not met")
    return tree

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="Auto")
    p.add_argument("--effort",default="default")
    args=p.parse_args()
    client=load_client()
    status=client.request("GET","/status")
    if not status.get("native_video"):raise RuntimeError("Native video flag is not enabled; no inference was started")
    if status.get("busy") or status.get("waiting_count"):raise RuntimeError("Worker is busy; no inference was started")
    job=str(uuid4());deadline=time.monotonic()+180
    data={"id":job,"model":args.model,"effort":args.effort,"timeout":180,
        "system":"Return Python source only. Do not invoke any external tools.",
        "prompt":"生成最小的Manim Python代码：导入manim，定义SmokeScene(Scene)，construct中仅添加一个显示 1+1=2 的MathTex。不要运行代码、不要输出解释。"}
    try:
        reply=client.request("POST","/video/start",data)
        while True:
            if reply.get("video_inference_mode")!="native_sdk":raise RuntimeError("video inference did not use native SDK")
            if reply["state"]=="done":
                validate_code(reply.get("answer",""))
                print("NATIVE_VIDEO_INFERENCE_PASSED (synthetic code syntax only; real Manim render and edit still required)",flush=True)
                return
            if reply["state"]!="running":raise RuntimeError("video inference failed: "+str(reply.get("detail",""))[:300])
            if time.monotonic()>=deadline:raise RuntimeError("video inference timeout")
            time.sleep(.5)
            reply=client.request("GET","/chat/"+job)
    finally:
        try:client.request("POST","/chat/"+job+"/cancel",{})
        except Exception:pass

if __name__=="__main__":main()
