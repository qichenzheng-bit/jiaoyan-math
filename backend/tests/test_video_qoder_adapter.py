import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location("video_qoder_adapter",Path(__file__).resolve().parents[2]/"deploy/video_qoder_adapter.py")
adapter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

def test_full_prompt_and_output(monkeypatch):
    prompt="题"*35000
    answer="x"*60000
    calls=[]
    def request(method,path,data=None):
        calls.append((method,path,data))
        return 200,{"state":"done","answer":answer}
    monkeypatch.setattr(adapter,"request",request)
    monkeypatch.setattr(adapter,"cancelled",lambda _:False)
    result=adapter.chat_cli("qoder_cli","socket","Auto",prompt=prompt,timeout=900)
    assert result["status"]=="ok" and result["text"]==answer
    assert calls[0][1]=="/video/start" and calls[0][2]["prompt"]==prompt

def test_reject_other_provider_or_oversize(monkeypatch):
    monkeypatch.setattr(adapter,"request",lambda *a,**k: (_ for _ in ()).throw(AssertionError("called worker")))
    assert adapter.chat_cli("codex_cli","","Auto",prompt="test")["status"]=="failed"
    assert adapter.chat_cli("qoder_cli","","Auto",prompt="题"*41000)["status"]=="failed"

def test_worker_unavailable(monkeypatch):
    monkeypatch.setattr(adapter,"request",lambda *a,**k:(200,{"available":True,"worker_version":4}))
    assert not adapter.target("qoder_cli")["installed"]

def test_cancel_propagates(monkeypatch):
    calls=[]
    def request(method,path,data=None):
        calls.append((method,path))
        return 200,{"state":"running","answer":""}
    check=iter([False,True])
    monkeypatch.setattr(adapter,"cancelled",lambda _:next(check))
    monkeypatch.setattr(adapter,"request",request)
    assert adapter.chat_cli("qoder_cli","","Auto",prompt="test")["status"]=="cancelled"
    assert calls[-1][1].endswith("/cancel")
