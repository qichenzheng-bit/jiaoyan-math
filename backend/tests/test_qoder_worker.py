import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("qoder_worker",Path(__file__).resolve().parents[2]/"deploy/qoder_worker.py")
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

def test_only_official_auth_links():
    assert worker.authorization_url("Open https://qoder.com.cn/auth/login?state=abc") == "https://qoder.com.cn/auth/login?state=abc"
    assert worker.authorization_url("Open https://qoder.cn/auth/login?state=abc") == "https://qoder.cn/auth/login?state=abc"
    assert worker.authorization_url("Open https://auth.qoder.cn/oauth?state=abc") == "https://auth.qoder.cn/oauth?state=abc"
    assert not worker.authorization_url("https://qoder.cn.evil.example/auth?state=abc")
    assert not worker.authorization_url("https://qoder.com.cn.evil.example/auth?state=abc")
    assert not worker.authorization_url("https://qoder.com.cn@evil.example/auth?state=abc")
    assert not worker.authorization_url("http://qoder.com.cn/auth")
    assert not worker.authorization_url("https://qoder.com.cn/")

def test_login_status_has_no_raw_credentials():
    result=worker.status()
    assert result["login"]["state"]=="idle"
    assert result["verified_at"] is None
    assert "auth_ui" in result

def test_model_catalog_parser():
    assert worker.parse_models("Warning: start\nMODEL\nAuto\nFast\nQwen4-Max\n--unsafe\nQwen4-Max") == ["Auto","Fast","Qwen4-Max"]
    assert worker.parse_models("Error: not authorized") == []

def test_model_restricted_to_catalog(monkeypatch):
    monkeypatch.setattr(worker,"catalog",["Qwen4-Max"])
    assert worker.allowed_model("Qwen4-Max")
    assert not worker.allowed_model("Auto")
    assert not worker.allowed_model("--help")
    monkeypatch.setattr(worker,"catalog",[])
    assert not worker.allowed_model("Auto")

def test_chat_events():
    assert worker.chat_event({"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"数学"}}})==("数学","",False)
    assert worker.chat_event({"type":"assistant","message":{"content":[{"type":"text","text":"结果"},{"type":"tool_use","input":{"secret":1}}]}})==("","结果",False)
    assert worker.chat_event({"type":"result","is_error":True})==("","",True)


def test_model_parser_rejects_option_like_rows():
    assert worker.parse_models('MODEL\n--unsafe\n- Auto\n* Fast') == ['Auto','Fast']

def test_durable_job_snapshot(tmp_path,monkeypatch):
    monkeypatch.setattr(worker,"SNAPSHOT_DIR",tmp_path)
    ident="12345678-1234-1234-1234-123456789abc"
    worker.save_snapshot({"id":ident,"state":"done","answer":"完成","detail":""})
    assert worker.load_snapshot(ident)["answer"]=="完成"
    assert worker.chat_state(ident)[0]==200
    assert worker.load_snapshot("../bad") is None
    worker.save_snapshot({"id":ident,"state":"running","answer":"","detail":""})
    assert worker.load_snapshot(ident)["state"]=="failed"


def test_video_request_rejects_oversize_and_unsafe_parameters(monkeypatch):
    monkeypatch.setattr(worker,"catalog",None)
    ident="12345678-1234-1234-1234-123456789abc"
    assert worker.chat_start({"id":ident,"model":"Auto","prompt":"题"*41000},video=True)[0]==422
    assert worker.chat_start({"id":ident,"model":"Auto","prompt":"ok","timeout":901},video=True)[0]==422
    assert worker.chat_start({"id":ident,"model":"Auto","prompt":"ok","effort":"--help"},video=True)[0]==422
    assert worker.chat_start({"id":ident,"model":"Auto","prompt":"ok","system":"x"*4097},video=True)[0]==422


def test_catalog_efforts_are_explicit_only():
    assert worker.parse_catalog('MODEL\nAuto\nFast')=={"Auto":[],"Fast":[]}
    assert worker.parse_catalog('{"models":[{"id":"Qwen","efforts":["high","low","--help"]},{"id":"Fast"}]}')=={"Qwen":["low","high"],"Fast":[]}
    assert worker.parse_catalog('MODEL\nAuto\nQwen efforts: low, high')=={"Auto":[],"Qwen":["low","high"]}


def test_official_model_info_thinking_config():
    import json
    rows=[{"value":"Qwen3.8-Max","isEnabled":True,"thinking_config":{"disabled":{},"enabled":{"efforts":{"high":{"is_default":True},"max":{},"--help":{}}}}},{"value":"Auto"},{"value":"Disabled","isEnabled":False,"efforts":["high"]}]
    result=worker.parse_catalog(json.dumps({"models":rows}))
    assert set(result["Qwen3.8-Max"])=={"disabled","high","max"}
    assert result["Auto"]==[] and "Disabled" not in result


def test_sdk_catalog_is_preferred(monkeypatch):
    monkeypatch.setattr(worker,"executable",lambda:"/usr/bin/qoderclicn")
    monkeypatch.setattr(worker,"sdk_catalog",lambda exe:({"Auto":[],"Qwen4-Max":["high","max"]},"sdk"))
    for key in ("catalog","catalog_at","catalog_efforts","catalog_capability_source"):
        monkeypatch.setattr(worker,key,getattr(worker,key))
    status,result=worker.refresh_models()
    assert status==200 and result["source"]=="cli"
    assert result["capability_source"]=="sdk"
    assert result["models"][1]["efforts"]==["high","max"]


def test_missing_sdk_is_safe(monkeypatch,tmp_path):
    monkeypatch.setattr(worker,"SDK_PYTHON",tmp_path/"missing")
    assert worker.sdk_catalog("/usr/bin/qoderclicn")== (None,"sdk_missing")
