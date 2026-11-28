from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from app.core import native_chat as n

def test_chat_only_read_only_native_tools():
    tools={t["name"]:t for t in n.tools()}
    assert "native_page" in tools and "native_suggest_work" in tools
    assert all(not t["write"] for t in tools.values())
    assert "native_intake_review" not in tools and "native_attach" not in tools
    assert "original_read" not in tools

def test_native_chat_flag(monkeypatch):
    monkeypatch.delenv("WG_NATIVE_CHAT",raising=False)
    assert not n.enabled()
    monkeypatch.setenv("WG_NATIVE_CHAT","1")
    assert n.enabled()

def test_resume_only_same_user_completed_native_session(monkeypatch):
    messages=[SimpleNamespace(id="a",position=2,role="assistant",state="done"),
              SimpleNamespace(id="b",position=4,role="assistant",state="done"),
              SimpleNamespace(id="c",position=6,role="assistant",state="failed")]
    states={"a":{"native":True,"native_actor":"u","native_session":"s1"},
            "b":{"native":True,"native_actor":"other","native_session":"s2"},
            "c":{"native":True,"native_actor":"u","native_session":"s3"}}
    monkeypatch.setattr(n.ai_chat,"load",lambda db,m:states.get(m.id))
    assert n.session_anchor(None,messages,SimpleNamespace(id="u"))==("s1",2)
    assert n.session_anchor(None,messages,SimpleNamespace(id="unknown"))==(None,0)

def test_chat_cannot_read_unattached_file():
    db=Mock()
    db.scalars.return_value=[SimpleNamespace(attachments=[{"id":"mine"}])]
    with pytest.raises(HTTPException) as exc:
        n.file_for_chat(db,SimpleNamespace(session_id="chat"),"other")
    assert exc.value.status_code==403
    db.get.assert_not_called()

def test_native_chat_pending_does_not_use_legacy_query(monkeypatch):
    db=Mock();m=SimpleNamespace(model="Auto",detail="")
    state={"job":"j","workspace":"w","resume":"old","prompt":"继续","system":"sys","effort":"default",
           "phase":"pending","at":n.now(),"steps":[]}
    request=Mock(return_value={"state":"running"})
    monkeypatch.setattr(n.qoder,"request",request)
    monkeypatch.setattr(n.ai_chat,"store",Mock())
    n.pending(db,m,state)
    method,path,body=request.call_args.args
    assert (method,path)==("POST","/agent/start") and body["resume"]=="old"
    assert body["prompt"]=="继续" and state["phase"]=="model"
