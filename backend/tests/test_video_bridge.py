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


def test_video_model_syncs_both_groups(monkeypatch):
    state={"other":{"configured":True,"mode":"qoder_cli","model_id":"Auto"},"edit":{"configured":True,"mode":"qoder_cli","model_id":"Fast"}}
    calls=[]
    def call(method,path,body=None):
        calls.append((method,path,body))
        if method=="PUT":
            for group in state.values():
                group["model_id"]=body["model_id"]
                group["reasoning_effort"]=body["reasoning_effort"]
            return {"configured":True,"model_id":body["model_id"]}
        return {"groups":state}
    monkeypatch.setattr(video_engine,"call",call)
    video_engine.configure_production_model("Fast")
    assert state["other"]["model_id"]==state["edit"]["model_id"]=="Fast"
    assert [p for m,p,b in calls if m=="PUT"]==["/ai/global"]
    calls.clear()
    video_engine.configure_production_model("Fast")
    assert [m for m,p,b in calls]==["GET"]

    video_engine.configure_production_model("Fast","high")
    assert all(group["reasoning_effort"]=="high" for group in state.values())


def test_video_effort_override_is_validated(monkeypatch):
    from app.api import video, qoder
    monkeypatch.setattr(qoder,"video_model_preference",lambda db:"Fast")
    monkeypatch.setattr(qoder,"stored_effort",lambda db,key:"medium")
    monkeypatch.setattr(qoder,"available_models",lambda:{"source":"cli","models":[{"id":"Fast","efforts":["medium","high"]}]})
    calls=[]
    monkeypatch.setattr(video_engine,"configure_production_model",lambda model,effort:calls.append((model,effort)))
    video.prepare_model(None)
    video.prepare_model(None,"high")
    assert calls==[("Fast","medium"),("Fast","high")]
    with pytest.raises(HTTPException) as exc:video.prepare_model(None,"max")
    assert exc.value.status_code==422
    assert len(calls)==2


def test_cover_selection_stores_reference(monkeypatch):
    from app.api import video
    from types import SimpleNamespace
    image=SimpleNamespace(archived=False,media_type="image/png")
    item=SimpleNamespace(id="work",data={"category":"video"})
    db=SimpleNamespace(get=lambda model,id:image)
    refs=[]
    monkeypatch.setattr(video.storage,"link_file",lambda db,file_id,owner,ident:refs.append((file_id,owner,ident)))
    body=video.CoverSelection(file_id="cover",timestamp=23.5,revision=3)
    video.save_cover(db,None,item,body)
    assert item.data["cover_file_id"]=="cover" and item.data["cover_timestamp"]==23.5
    assert item.data["cover_revision"]==3 and refs==[("cover","studio_item","work")]
    image.media_type="image/jpeg"
    with pytest.raises(HTTPException):video.save_cover(db,None,item,body)


def test_video_snapshot_uses_only_recommended_method():
    from app.core.solution_methods import format_methods
    r=SimpleNamespace(title="极限",content="求极限",solution=format_methods([{"body":"方法甲","recommended":False},{"body":"方法乙","recommended":True}]),answer="0",subject="高等数学",chapter="",exam_type="",question_type="综合题",analysis="",tags=[],question_data=None)
    assert snapshot(r)["reference_solution"]=="方法乙"
