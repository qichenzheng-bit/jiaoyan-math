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


def test_supplement_preserves_base_prompt(monkeypatch):
    calls=[]
    monkeypatch.setattr(adapter,"job_supplement",lambda:"逐步书写")
    monkeypatch.setattr(adapter,"cancelled",lambda _:False)
    def request(method,path,data=None):
        calls.append(data)
        return 200,{"state":"done","answer":"code"}
    monkeypatch.setattr(adapter,"request",request)
    result=adapter.chat_cli("qoder_cli","socket","Auto",prompt="固定教学内容")
    assert result["status"]=="ok"
    assert calls[0]["prompt"].startswith("固定教学内容")
    assert "逐步书写" in calls[0]["prompt"] and "固定教学规范" in calls[0]["prompt"]

def test_prompt_route_requires_token_and_preserves_task_context(monkeypatch):
    from fastapi import APIRouter,FastAPI
    from fastapi.testclient import TestClient
    router=APIRouter()
    seen=[]
    @router.post("/lessons/{id}/generate")
    def generate(id:str):
        seen.append((id,adapter._job_prompt.get()))
        return {"id":id,"status":"queued"}
    app=FastAPI()
    app.include_router(adapter.add_prompt_routes(router),prefix="/api/v1")
    monkeypatch.setenv("WEIGUANG_API_TOKEN","test-only")
    with TestClient(app) as client:
        url="/api/v1/jiaoyan/lessons/test/generate"
        body={"text":"逐步推导","revision":2}
        assert client.post(url,json=body).status_code==403
        assert not seen
        response=client.post(url,json=body,headers={"X-API-Key":"test-only"})
        assert response.status_code==202,response.text
        assert seen==[("test",body)]
        assert adapter._job_prompt.get() is None
        assert client.get("/api/v1/jiaoyan/prompt-capability",headers={"X-API-Key":"test-only"}).json()["snapshot"]=="job"
