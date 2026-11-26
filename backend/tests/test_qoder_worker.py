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


def test_sdk_catalog_is_preferred(monkeypatch,tmp_path):
    monkeypatch.setattr(worker,"AUTH_STATE_PATH",tmp_path/"auth.json")
    monkeypatch.setattr(worker,"retained_auth",False)
    monkeypatch.setattr(worker,"login",dict(worker.login))
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


def test_sdk_display_names_match_cli_preferences():
    rows=[
      {"value":"qmodel_latest","displayName":"Qwen4-Max","isEnabled":True,"thinking_config":{"disabled":{},"enabled":{"efforts":{"xhigh":{},"high":{"is_default":True},"low":{}}}}},
      {"value":"auto","displayName":"Auto","thinking_config":None},
      {"value":"dmodel","displayName":"DeepSeek-V4-Pro","thinking_config":{"enabled":{"efforts":{"high":{},"max":{}}}}},
      {"value":"gmodel","displayName":"GLM-5.3","isEnabled":False,"thinking_config":{"enabled":{"efforts":{"high":{}}}}},
      {"value":"unknown","thinking_config":{"enabled":{"efforts":{"high":{}}}}}
    ]
    assert worker.parse_sdk_catalog({"models":rows})=={"Qwen4-Max":["disabled","low","high","xhigh"],"Auto":[],"DeepSeek-V4-Pro":["high","max"]}


def test_retained_auth_survives_restart_and_explicit_disconnect(monkeypatch,tmp_path):
    import json
    monkeypatch.setattr(worker,"AUTH_STATE_PATH",tmp_path/"auth.json")
    for key in ("retained_auth","user_disconnected","verified_at","catalog","catalog_at","catalog_efforts","catalog_capability_source"):
        monkeypatch.setattr(worker,key,getattr(worker,key))
    monkeypatch.setattr(worker,"login",dict(worker.login))
    monkeypatch.setattr(worker,"executable",lambda:"/usr/bin/qoderclicn")
    monkeypatch.setattr(worker,"retained_auth",True)
    monkeypatch.setattr(worker,"verified_at",int(worker.time.time()))
    worker.save_auth_state()
    worker.retained_auth=False
    worker.verified_at=None
    worker.restore_auth_state()
    assert worker.status()["retained_auth"] and worker.status()["verified_at"]
    assert worker.disconnect()[0]==200
    worker.user_disconnected=False
    worker.restore_auth_state()
    assert worker.status()["user_disconnected"] and not worker.status()["chat_available"]
    assert worker.refresh_models()[0]==409
    assert worker.chat_start({"id":"12345678-1234-1234-1234-123456789abc","model":"Auto","prompt":"test"})[0]==409
    assert set(json.loads(worker.AUTH_STATE_PATH.read_text()))=={"retained","disconnected","verified_at","catalog","catalog_at","capability_source"}


def test_usage_parser_never_exposes_secrets_or_invents_zero():
    assert worker.parse_usage({"session":{"total_credits":12},"userId":"secret"}) is None
    data=worker.parse_usage({"userId":"secret","userQuota":{"total":100,"used":0,"remaining":100,"unit":"credits"},"addOnQuota":{"remaining":42},"orgResourcePackage":{"cap":200,"remaining":0,"available":False},"isQuotaExceeded":False})
    assert "secret" not in str(data)
    assert data["packs"][0]["used"]==0
    assert data["packs"][1]["total"] is None
    assert data["packs"][2]["total"]==200 and data["packs"][2]["available"] is False

def test_usage_refresh_cache_and_disconnect(monkeypatch):
    monkeypatch.setattr(worker,"usage_cache",None)
    monkeypatch.setattr(worker,"user_disconnected",False)
    monkeypatch.setattr(worker,"executable",lambda:"/usr/bin/qoderclicn")
    calls=[]
    def fetch(exe):
        calls.append(exe)
        return {"packs":[{"remaining":100}],"quota_exceeded":False},"sdk"
    monkeypatch.setattr(worker,"sdk_usage",fetch)
    assert worker.usage_status(True)[1]["available"]
    assert worker.usage_status(True)[1]["source"]=="sdk"
    assert len(calls)==1
    monkeypatch.setattr(worker,"user_disconnected",True)
    assert not worker.usage_status(True)[1]["available"]


def test_usage_api_distinguishes_old_worker_and_outage(monkeypatch):
    from fastapi import HTTPException
    from app.api import qoder
    for status, reason in ((404,"worker_upgrade_required"),(503,"worker_unavailable"),(504,"sdk_timeout")):
        def fail(*args, **kwargs):
            raise HTTPException(status, "internal error")
        monkeypatch.setattr(qoder, "request", fail)
        expected = {"available":False,"reason":reason}
        assert qoder.usage() == expected
        assert qoder.usage_refresh() == expected
