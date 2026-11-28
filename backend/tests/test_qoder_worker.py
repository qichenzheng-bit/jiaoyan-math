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

def test_vision_attachment_rejects_paths_and_invalid_media():
    import base64
    import pytest
    raw=b"\x89PNG\r\n\x1a\nexample"
    encoded=base64.b64encode(raw).decode()
    assert worker.vision_attachment({"media_type":"image/png","base64":encoded})==(".png",raw)
    for value in ({"path":"/etc/passwd"},{"media_type":"image/png","base64":"!"},{"media_type":"text/plain","base64":encoded},{"media_type":"image/jpeg","base64":encoded}):
        with pytest.raises(ValueError):worker.vision_attachment(value)

def test_native_skill_bundle(tmp_path):
    worker.install_native_skills(tmp_path)
    for name,content in worker.NATIVE_SKILLS.items():
        assert (tmp_path/".qoder-cn"/"skills"/name/"SKILL.md").read_text(encoding="utf-8")==content+"\n"
    assert len(worker.NATIVE_SKILLS)>=4

def test_native_sdk_has_visible_mcp_tools_and_safe_subagent():
    import ast
    ast.parse(worker.SDK_AGENT_SCRIPT)
    assert "tools=[*builtins,*names]" in worker.SDK_AGENT_SCRIPT
    assert "allowed_tools=[*builtins,*names]" in worker.SDK_AGENT_SCRIPT
    assert "maxResultSizeChars" in worker.SDK_AGENT_SCRIPT
    assert "tools=read_names" in worker.SDK_AGENT_SCRIPT
    assert "setting_sources=[\"project\"]" in worker.SDK_AGENT_SCRIPT

def test_native_session_mirror_order_isolation_and_replay(tmp_path):
    import asyncio
    scope={}
    exec(worker.SDK_SESSION_STORE_SCRIPT,scope)
    store=scope["NativeSessionStore"](tmp_path/"mirror.sqlite3")
    async def scenario():
        a={"project_key":"p","session_id":"a"}
        child={**a,"subpath":"subagents/agent-1"}
        other={"project_key":"p","session_id":"b"}
        first={"type":"user","uuid":"1","text":"第一轮"}
        second={"type":"assistant","uuid":"2","text":"第二轮"}
        await store.append(a,[first,second])
        await store.append(a,[first,second])
        await store.append(child,[{"type":"assistant","uuid":"3"}])
        await store.append(other,[first])
        assert await store.load(a)==[first,second]
        assert await store.list_subkeys(a)==["subagents/agent-1"]
        reopened=scope["NativeSessionStore"](tmp_path/"mirror.sqlite3")
        assert await reopened.load(a)==[first,second]
        await reopened.delete(a)
        assert await reopened.load(a) is None and await reopened.load(child) is None
        assert await reopened.load(other)==[first]
    asyncio.run(scenario())

def test_native_session_mirror_rejects_path_traversal(tmp_path):
    import asyncio,pytest
    scope={}
    exec(worker.SDK_SESSION_STORE_SCRIPT,scope)
    store=scope["NativeSessionStore"](tmp_path/"mirror.sqlite3")
    with pytest.raises(ValueError):asyncio.run(store.append({"project_key":"p","session_id":"a","subpath":"../other"},[{"type":"x"}]))

def test_native_sdk_waits_for_memory_and_store_drain():
    import ast
    ast.parse(worker.SDK_AGENT_SCRIPT)
    assert "session_store=store" in worker.SDK_AGENT_SCRIPT
    assert "await client.flush_memory()" in worker.SDK_AGENT_SCRIPT
    assert "user_scope" in worker.SDK_AGENT_SCRIPT and '"user_scope":False' in worker.SDK_AGENT_SCRIPT
    assert "emit(final or" in worker.SDK_AGENT_SCRIPT


def test_native_video_preserves_prompt_contract(monkeypatch):
    import ast
    ast.parse(worker.SDK_VIDEO_SCRIPT)
    assert 'await client.query(cfg["prompt"])' in worker.SDK_VIDEO_SCRIPT
    assert 'opts["system_prompt"]=cfg["system"]' in worker.SDK_VIDEO_SCRIPT
    assert '"skills":[]' in worker.SDK_VIDEO_SCRIPT and '"tools":[]' in worker.SDK_VIDEO_SCRIPT
    assert 'opts["memory"]={}' in worker.SDK_VIDEO_SCRIPT
    monkeypatch.delenv("WG_NATIVE_VIDEO",raising=False)
    assert not worker.native_video_enabled()
    monkeypatch.setenv("WG_NATIVE_VIDEO","1")
    assert worker.native_video_enabled()

def test_native_sdk_missing_is_not_ready(tmp_path,monkeypatch):
    monkeypatch.setattr(worker,"SDK_PYTHON",tmp_path/"missing")
    assert worker.check_native_sdk()=={"ready":False,"memory":False,"reason":"sdk_missing"}

def test_native_workspace_delete_preserves_other_sessions_and_memory(tmp_path,monkeypatch):
    from uuid import uuid4
    workspace,session,other,job=map(str,[uuid4(),uuid4(),uuid4(),uuid4()])
    monkeypatch.setattr(worker.Path,"home",lambda:tmp_path)
    monkeypatch.setattr(worker,"SNAPSHOT_DIR",tmp_path/"results")
    monkeypatch.delenv("QODERCN_CONFIG_DIR",raising=False)
    cwd=worker.native_workspace_dir(workspace);cwd.mkdir(parents=True)
    (cwd/"owner").write_text("1")
    worker.remember_native_run(cwd,session,job)
    (cwd/"session-mirror.sqlite3").write_text("mirror")
    project=tmp_path/".qoder-cn"/"projects"/("project-"+workspace);project.mkdir(parents=True)
    (project/(session+".jsonl")).write_text("transcript")
    (project/session).mkdir()
    (project/session/"state.json").write_text("{}")
    (project/(other+".jsonl")).write_text("other")
    memory=tmp_path/".jiaoyan-native-memory"/"1";memory.mkdir(parents=True)
    (memory/"MEMORY.md").write_text("preference")
    assert worker.remove_native_workspace({"workspace":workspace,"owner":2})[0]==403
    assert worker.remove_native_workspace({"workspace":workspace,"owner":1})[0]==200
    assert not cwd.exists() and not (project/(session+".jsonl")).exists() and not (project/session).exists()
    assert (project/(other+".jsonl")).exists() and (memory/"MEMORY.md").exists()

def test_native_workspace_delete_refuses_ambiguous_cli_path(tmp_path,monkeypatch):
    from uuid import uuid4
    workspace,session=str(uuid4()),str(uuid4())
    monkeypatch.setattr(worker.Path,"home",lambda:tmp_path)
    monkeypatch.delenv("QODERCN_CONFIG_DIR",raising=False)
    cwd=worker.native_workspace_dir(workspace);cwd.mkdir(parents=True)
    (cwd/"owner").write_text("1")
    worker.remember_native_run(cwd,session)
    project=tmp_path/".qoder-cn"/"projects"/"other-project";project.mkdir(parents=True)
    local=project/(session+".jsonl");local.write_text("keep")
    assert worker.remove_native_workspace({"workspace":workspace,"owner":1})[0]==409
    assert local.exists() and cwd.exists()


def test_native_sdk_uses_bundled_cli(monkeypatch):
    monkeypatch.setenv("QODERCN_PATH","/legacy/incompatible/qoderclicn")
    monkeypatch.setenv("HOME","/test/worker")
    env=worker.sdk_environment()
    assert "QODERCN_PATH" not in env and env["HOME"]=="/test/worker"
    assert "cli_path=" not in worker.SDK_AGENT_SCRIPT
    assert '"cli_path":' not in worker.SDK_VIDEO_SCRIPT
    assert 'code==42' in worker.SDK_AGENT_SCRIPT


def test_native_interrupt_only_at_safe_tool_boundary(monkeypatch):
    from unittest.mock import Mock
    ident="test-native"
    proc=Mock()
    job={"native":True,"state":"running","proc":proc,"interrupt_ready":True,"pending":{"id":"tool"}}
    monkeypatch.setitem(worker.chat_jobs,ident,job)
    assert worker.agent_interrupt(ident)[0]==409
    proc.send_signal.assert_not_called()
    job.pop("pending")
    assert worker.agent_interrupt(ident)[0]==200
    proc.send_signal.assert_called_once_with(worker.signal.SIGUSR1)
    assert worker.agent_interrupt(ident)[0]==200
    assert proc.send_signal.call_count==1


def test_native_interrupt_pipe_read_is_cancellable():
    import ast
    ast.parse(worker.SDK_AGENT_SCRIPT)
    assert "await reader.readline()" in worker.SDK_AGENT_SCRIPT
    assert "asyncio.to_thread(sys.stdin.readline)" not in worker.SDK_AGENT_SCRIPT


def test_model_admission_fairness_expiry_and_cancellation(monkeypatch):
    monkeypatch.setattr(worker,"MODEL_WAITERS",{})
    monkeypatch.setattr(worker,"chat_active","active")
    monkeypatch.setattr(worker,"login_process",None)
    assert not worker.model_admission("first",True,0)
    assert not worker.model_admission("second",True,1)
    monkeypatch.setattr(worker,"chat_active",None)
    assert not worker.model_admission("second",True,2)
    assert not worker.model_admission("unregistered",False,2)
    assert worker.model_admission("first",True,3)
    assert worker.model_admission("second",True,4)
    monkeypatch.setattr(worker,"chat_active","active")
    assert not worker.model_admission("abandoned",True,5)
    worker.prune_model_waiters(36)
    assert not worker.MODEL_WAITERS
    assert not worker.model_admission("cancelled",True,37)
    assert worker.chat_state("cancelled",True)[1]["state"]=="stopped"
    assert not worker.MODEL_WAITERS
