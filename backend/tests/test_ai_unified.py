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
    r={"instruction":"分析真题","preference_snapshot":"偏好"*8000,"steps":[{"tool":"question_search","args":{},"state":"done","result":{"content":"题"*12000}}]*8}
    assert len(ai_work.later_prompt(r).encode())<=100000
    assert ai_work.json_reply('{"action":"finish"}')["action"]=="finish"
    with pytest.raises(ValueError):ai_work.json_reply("[]")
    assert "selection_create" not in ai_chat.protocol()

def test_work_executes_actual_tool_without_confirmation(monkeypatch):
    from app.api import work_agent as wa, qoder
    user=SimpleNamespace(id=1)
    s=SimpleNamespace(id="w",agent_history=[])
    r={"id":"r","model":"Auto","effort":"default","model_job":"m","phase":"model","phase_at":ai_work.now(),"state":"running","instruction":"查询题目","steps":[]}
    s.agent_history=[r]
    def save(db,s,r):s.agent_history=[dict(r)]
    monkeypatch.setattr(wa,"save",save)
    monkeypatch.setattr(ai_work,"wa_session",lambda db,ident:s)
    monkeypatch.setattr(ai_work,"audit",lambda *args:None)
    monkeypatch.setattr(qoder,"request",lambda *args:{"state":"done","answer":json.dumps({"action":"tool","tool":"question_search","args":{}})})
    run=Mock(return_value={"total":1,"items":[{"id":"real","title":"实际题目"}]})
    monkeypatch.setattr(ai_tools,"execute",run)
    db=Mock()
    ai_work.run_model(db,s,r,user)
    run.assert_called_once()
    saved=s.agent_history[-1]
    assert saved["steps"][0]["result"]["items"][0]["id"]=="real"
    assert saved["steps"][0]["state"]=="done" and saved["phase"]=="pending"
    assert saved["state"]=="running"

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
    assert result["needs_replan"] and "改为30题" in ai_work.later_prompt(r)

def test_child_tracking_uses_real_job_id():
    assert ai_work.child_task("video_generate",{"ident":"p"},{"id":"job","status":"queued"})=={"kind":"video","project":"p","id":"job"}
    assert ai_work.child_task("video_edit",{"ident":"p"},{"job":{"id":"edit-job"}})["id"]=="edit-job"
    assert ai_work.child_task("question_search",{},{"id":"question"}) is None
    assert ai_work.child_task("intake_text",{},{"id":"intake","state":"running"})=={"kind":"intake","id":"intake"}

def test_planning_does_not_count_as_business_result(monkeypatch):
    from app.api import work_agent as wa, qoder
    monkeypatch.setattr(wa,"save",lambda db,s,r:setattr(s,"agent_history",[dict(r)]))
    s=SimpleNamespace(agent_history=[],id="w")
    r={"id":"r","model":"Auto","effort":"default","model_job":"m","phase":"model","phase_at":ai_work.now(),"state":"running","instruction":"选题","steps":[]}
    s.agent_history=[r]
    monkeypatch.setattr(qoder,"request",lambda *args:{"state":"done","answer":json.dumps({"action":"plan","outline":["检索题库","生成试卷"]})})
    ai_work.run_model(Mock(),s,r,SimpleNamespace(id=1))
    planned=s.agent_history[-1]
    assert planned["outline"]==["检索题库","生成试卷"] and planned["phase"]=="pending"
    planned["phase"]="model"
    monkeypatch.setattr(qoder,"request",lambda *args:{"state":"done","answer":json.dumps({"action":"finish","explanation":"完成"})})
    ai_work.run_model(Mock(),s,planned,SimpleNamespace(id=1))
    assert s.agent_history[-1]["state"]=="failed"
