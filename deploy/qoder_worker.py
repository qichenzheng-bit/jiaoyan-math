#!/usr/bin/env python3
"""Unix socket-only Qoder CN worker. Run under a separate non-root user."""
import json
import os
import shutil
import signal
import socketserver
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler

SOCKET="/run/jiaoyan-qoder/worker.sock"
def executable():
    return shutil.which("qoderclicn")
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,status,data):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path!="/status": return self.reply(404,{"detail":"Not found"})
        self.reply(200,{"available":bool(executable()),"detail":"CLI 已检测到；账号授权和模型可用性以实际测试为准" if executable() else "未检测到 qoderclicn"})
    def do_POST(self):
        if self.path!="/test": return self.reply(404,{"detail":"Not found"})
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<=64000: raise ValueError()
            data=json.loads(self.rfile.read(n))
            model=data["model"];prompt=data["prompt"]
            if model not in ("Auto","Fast") or not isinstance(prompt,str) or not 0<len(prompt.strip())<=12000: raise ValueError()
        except (ValueError,KeyError,TypeError): return self.reply(422,{"detail":"参数不正确"})
        exe=executable()
        if not exe: return self.reply(503,{"detail":"未安装 Qoder CN CLI"})
        with tempfile.TemporaryDirectory(prefix="qoder-test-") as work:
            try:
                proc=subprocess.Popen([exe,"-m",model,"--tools","","--no-session-persistence","-p","请直接回答以下数学或教研问题，不调用工具：\n"+prompt],cwd=work,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
                try:
                    out,err=proc.communicate(timeout=40)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL);proc.communicate()
                    return self.reply(504,{"detail":"模型调用超时，请在服务器确认授权及网络"})
                if proc.returncode!=0:
                    return self.reply(503,{"detail":"CLI 调用失败，请在服务器使用相同账号检查登录及 CLI 参数"})
                answer=out.decode("utf-8",errors="replace").strip()
                if not answer: return self.reply(503,{"detail":"CLI 未返回正文"})
                return self.reply(200,{"model":model,"answer":answer[:30000]})
            except OSError: return self.reply(503,{"detail":"CLI 无法启动"})
class Server(socketserver.UnixStreamServer):
    def get_request(self):
        conn,addr=super().get_request()
        conn.settimeout(5)
        return conn,addr
if __name__=="__main__":
    if os.geteuid()==0: raise SystemExit("Do not run as root")
    if os.path.exists(SOCKET): os.unlink(SOCKET)
    with Server(SOCKET,Handler) as server:
        os.chmod(SOCKET,0o660)
        server.serve_forever()
