"""Server-side daily Qoder catalog refresh; no real CLI calls."""
from fastapi import HTTPException
from app.api import qoder

def fixture(monkeypatch, *, updated_at=1000, source="cli", status=None, fail=False):
    calls = []
    state = {"available": True, "model_discovery": True, "busy": False}
    if status:
        state.update(status)
    catalog = {"source": source, "updated_at": updated_at, "models": [{"id": "Auto"}]}
    def request(method, path, body=None):
        calls.append((method, path))
        if path == "/status":
            return state
        if path == "/models":
            return catalog
        if fail:
            raise HTTPException(503, "unavailable")
        return {"source": "cli", "updated_at": 90000, "models": [{"id": "Latest"}]}
    monkeypatch.setattr(qoder, "request", request)
    monkeypatch.setattr(qoder, "last_refresh_success", 0.0)
    return calls

def test_fresh_catalog_is_not_refetched(monkeypatch):
    calls = fixture(monkeypatch)
    assert qoder.refresh_if_due(1000 + 86399) == "fresh"
    assert ("POST", "/models/refresh") not in calls

def test_due_catalog_refreshed(monkeypatch):
    calls = fixture(monkeypatch)
    assert qoder.refresh_if_due(1000 + 86400) == "updated"
    assert calls.count(("POST", "/models/refresh")) == 1

def test_missing_catalog_refreshed_on_startup(monkeypatch):
    calls = fixture(monkeypatch, updated_at=None, source="fallback")
    assert qoder.refresh_if_due(1000) == "updated"
    assert ("POST", "/models/refresh") in calls

def test_busy_or_login_deferred(monkeypatch):
    for status in ({"busy": True}, {"login": {"state": "waiting"}}, {"available": False}):
        calls = fixture(monkeypatch, status=status)
        assert qoder.refresh_if_due(100000) in ("busy", "unavailable")
        assert ("POST", "/models/refresh") not in calls

def test_failure_retries_and_lock_released(monkeypatch):
    calls = fixture(monkeypatch, fail=True)
    assert qoder.refresh_if_due(100000) == "retry"
    assert qoder.refresh_if_due(100000) == "retry"
    assert calls.count(("POST", "/models/refresh")) == 2

def test_manual_refresh_still_works(monkeypatch):
    calls = fixture(monkeypatch)
    assert qoder.models_refresh()["models"] == [{"id": "Latest"}]
    assert calls == [("POST", "/models/refresh")]
