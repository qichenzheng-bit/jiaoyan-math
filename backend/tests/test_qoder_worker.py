import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("qoder_worker",Path(__file__).resolve().parents[2]/"deploy/qoder_worker.py")
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

def test_only_official_auth_links():
    assert worker.authorization_url("Open https://qoder.com.cn/auth/login?state=abc") == "https://qoder.com.cn/auth/login?state=abc"
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
