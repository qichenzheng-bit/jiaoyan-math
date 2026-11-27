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
