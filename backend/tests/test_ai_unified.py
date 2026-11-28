import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.core import ai_tools, ai_work, ai_chat, ai_preferences

def test_tool_allowlist_and_real_schema():
    assert len(ai_tools.TOOLS)>=30
    assert all(not x["write"] for x in ai_tools.catalogue("chat"))
    assert "question_search" in {x["name"] for x in ai_tools.catalogue("chat")}
    for name in ("delete_resource","selection_create","document_patch","video_generate"):
        with pytest.raises(HTTPException) as exc:
            ai_tools.execute(name,{},None,None,mode="chat")
        assert exc.value.status_code==403
    with pytest.raises(ValidationError):
        ai_tools.TOOLS["question_search"].schema.model_validate({"kind":"source"})
    with pytest.raises(ValidationError):
        ai_tools.TOOLS["original_read"].schema.model_validate({"body":{"file_id":"f","mode":"shell"}})

def test_selection_checks_before_write():
    for ids,scores,total in [(["a","a"],[10,10],20),(["a"],[10],100),(["a","b"],[10],10)]:
        db=Mock()
        with pytest.raises(HTTPException):
            ai_tools.create_selection(ai_tools.Selection(title="测试",kind="paper",resource_ids=ids,scores=scores,total_score=total),db,None)
        db.get.assert_not_called()

def test_bounded_results_and_prompt():
    result=ai_tools.bounded_result({"total":100,"items":[{"id":str(i),"title":"题"*1000} for i in range(100)]})
    assert result["truncated"] and result["total"]==100 and result["items"][0]["id"]=="0"
    assert len(json.dumps(result,ensure_ascii=False))<=12000
    from app.core import native_chat
    assert "selection_create" not in {t["name"] for t in native_chat.tools()}

def test_preference_scope_and_history(monkeypatch):
    values={}
    db=Mock()
    user=SimpleNamespace(id=1)
    monkeypatch.setattr(ai_preferences,"read",lambda db,k,default:values.get(k,default))
    monkeypatch.setattr(ai_preferences,"save",lambda db,k,data:values.__setitem__(k,data))
    ai_preferences.set_memory(db,user,ai_preferences.MemoryUpdate(revision=0,items=[{"id":"x","text":"公式使用LaTeX","scope":"work"},{"id":"y","text":"仅聊天","scope":"chat"}]))
    for i in range(4):
        ai_preferences.set_prompt(db,user,"work",ai_preferences.PromptUpdate(revision=i,text=str(i)))
    assert "公式使用LaTeX" in ai_preferences.context(db,user,"work")
    assert "仅聊天" not in ai_preferences.context(db,user,"work")
    assert len(ai_preferences.prompt(db,user,"work")["history"])==2
    with pytest.raises(HTTPException):ai_preferences.set_prompt(db,user,"work",ai_preferences.PromptUpdate(revision=0,text="old"))

def test_cover_draft_is_editable_and_rejects_unsafe_layers():
    from app.core.ai_cover import CoverDraft,build
    valid={"name":"封面","format":"xiaohongshu","layers":[{"kind":"text","content":"高等数学","x":10,"y":10,"w":80,"h":20}]}
    design=build(CoverDraft.model_validate(valid),Mock())
    assert design["width"]==1080 and design["layers"][0]["x"]==108
    with pytest.raises(ValidationError):
        CoverDraft.model_validate({**valid,"layers":[{**valid["layers"][0],"kind":"image","content":"https://unknown.example"}]})
    with pytest.raises(HTTPException):
        build(CoverDraft.model_validate({**valid,"layers":[{**valid["layers"][0],"x":50}]}),Mock())

def test_amendment_retains_existing_results(monkeypatch):
    from app.api import work_agent as wa
    monkeypatch.setattr(ai_work,"audit",lambda *args:None)
    monkeypatch.setattr(wa,"save",lambda db,s,r:setattr(s,"agent_history",[dict(r)]))
    s=SimpleNamespace(agent_history=[])
    r={"id":"r","actor_id":1,"instruction":"选20题","state":"running","steps":[{"tool":"question_search","state":"done","result":{"total":50}}]}
    body=wa.Start(instruction="改为30题")
    result=ai_work.revise(Mock(),s,r,body,SimpleNamespace(id=1))
    assert result["steps"][0]["result"]["total"]==50
    assert result["amendments"][-1]["text"]=="改为30题"

def test_child_tracking_uses_real_job_id():
    assert ai_work.child_task("video_generate",{"ident":"p"},{"id":"job","status":"queued"})=={"kind":"video","project":"p","id":"job"}
    assert ai_work.child_task("video_edit",{"ident":"p"},{"job":{"id":"edit-job"}})["id"]=="edit-job"
    assert ai_work.child_task("question_search",{},{"id":"question"}) is None
    assert ai_work.child_task("intake_text",{},{"id":"intake","state":"running"})=={"kind":"intake","id":"intake"}

def test_retiring_legacy_work_keeps_business_receipts(monkeypatch):
    from app.api import work_agent as wa, qoder
    monkeypatch.setattr(wa,"save",lambda db,s,r:setattr(s,"agent_history",[dict(r)]))
    cancel=Mock(return_value={"state":"stopped"});monkeypatch.setattr(qoder,"request",cancel)
    record={"id":"r","state":"running","phase":"model","model_job":"old","steps":[{"state":"done","result":{"id":"saved"}}],"prompt":"old protocol"}
    result=ai_work.retire_old(Mock(),SimpleNamespace(),record)
    assert result["state"]=="failed" and result["steps"][0]["result"]["id"]=="saved"
    assert "prompt" not in result
    cancel.assert_called_once_with("POST","/chat/old/cancel",{})
