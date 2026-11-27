from app.core.config import settings
from app.core.ai_work import completion_problem

def step(i, tool, state="done", args=None):
    return {"step_index":i,"tool":tool,"state":state,"args":args or {}}

def test_v1_and_upload_limit():
    assert settings.version == "V1"
    assert settings.max_file_bytes == 200 * 1024 * 1024

def test_planned_work_cannot_claim_partial_success():
    r={"outline":["search","create"],"steps":[step(0,"question_search")]}
    assert completion_problem(r)
    r["steps"].append(step(1,"selection_create","failed"))
    assert completion_problem(r)
    r["steps"].append(step(1,"selection_create"))
    assert not completion_problem(r)
    r["outline_stale"]=True
    assert completion_problem(r)

def test_replanned_work_needs_new_evidence():
    r={"outline":["new task"],"steps":[step(0,"question_search"),{"tool":"plan","state":"done"}]}
    assert completion_problem(r)
    r["steps"].append(step(0,"question_search"))
    assert not completion_problem(r)


def test_expected_write_cannot_be_replaced_by_read():
    r={"outline":["create"],"expected_tools":["selection_create"],"steps":[step(0,"question_search")]}
    assert completion_problem(r)
    r["steps"].append(step(0,"selection_create"))
    assert not completion_problem(r)

def test_corrected_retry_resolves_only_explicit_failed_operation():
    bad={**step(0,"question_search","failed",{"q":"wrong"}),"id":"old","retryable":True}
    good={**step(0,"question_search","done",{"q":"right"}),"retry_of":"old"}
    r={"outline":["search"],"expected_tools":["question_search"],"steps":[bad,good]}
    assert not completion_problem(r)
    bad["retryable"]=False
    assert completion_problem(r)

def test_original_progress_filter_before_pagination(monkeypatch):
    from unittest.mock import Mock
    from app.api import workspaces
    db=Mock()
    db.scalars.return_value.partitions.return_value=iter([[{"complete":False} for _ in range(100)],[{"complete":True,"id":"match"}]])
    monkeypatch.setattr(workspaces,"library_details",lambda db,part:(part,{},{}))
    result=workspaces.library(q="",archived=False,offset=0,limit=50,db=db,progress_filter="done")
    assert result=={"items":[{"complete":True,"id":"match"}],"total":1}
