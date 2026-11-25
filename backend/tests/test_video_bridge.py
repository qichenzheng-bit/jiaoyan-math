import pytest
from fastapi import HTTPException
from app.services import video_engine
from app.api.video import snapshot
from types import SimpleNamespace

def test_bridge_requires_configuration(monkeypatch):
    monkeypatch.delenv("VIDEO_ENGINE_TOKEN",raising=False)
    with pytest.raises(HTTPException) as e: video_engine.config()
    assert e.value.status_code==503

def test_bridge_is_loopback_and_validates_id(monkeypatch):
    monkeypatch.setenv("VIDEO_ENGINE_TOKEN","test-token")
    monkeypatch.setenv("VIDEO_ENGINE_PORT","8766")
    assert video_engine.config()[0]=="http://127.0.0.1:8766/api/v1"
    with pytest.raises(HTTPException): video_engine.engine_id("../../admin")
    assert video_engine.engine_id("a"*32)=="a"*32

def test_snapshot_preserves_math_and_rejects_missing_solution():
    r=SimpleNamespace(title="极限",content=r"$\lim_{x\to0} x$",solution="直接代入",answer="$0$",subject="高等数学",chapter="",exam_type="",question_type="",analysis="",tags=[])
    out=snapshot(r)
    assert out["problem"]==r.content and out["fps"]==60
    r.solution=""
    with pytest.raises(HTTPException): snapshot(r)
