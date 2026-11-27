import pytest
from app.api.work_agent import parse_intent
def test_work_agent_model_output_allowlist():
    i=parse_intent('{"action":"recognize","file_id":"f","count":5}',{"f"})
    assert i.count==5 and i.start is None
    for raw in ('{"action":"delete","file_id":"f"}','{"action":"recognize","file_id":"f","count":11}','{"action":"recognize","file_id":"f","count":"5"}','{"action":"attach","file_id":"unknown"}','{"action":"attach","file_id":"f","reference_ids":["unknown"]}','{"action":"review","file_id":"f"}','{"action":"attach","file_id":"f","shell":"rm"}'):
        with pytest.raises(ValueError):parse_intent(raw,{"f"})
    assert parse_intent('{"action":"clarify","explanation":"哪一本？"}',{"f"}).action=="clarify"


def test_goal_is_explicit_and_bounded():
    from app.api.work_agent import parse_intent
    assert parse_intent('{"action":"recognize","file_id":"f","count":5}',{"f"}).goal=="recognition"
    assert parse_intent('{"action":"recognize","file_id":"f","count":5,"goal":"review"}',{"f"}).goal=="review"
    with pytest.raises(ValueError):parse_intent('{"action":"recognize","file_id":"f","count":5,"goal":"auto_register"}',{"f"})


def test_planned_match_requires_reference_and_review():
    from app.api.work_agent import parse_intent,missing_match_items
    raw='{"action":"recognize","file_id":"f","count":5,"goal":"review","reference_ids":["r"],"match_fields":["answer"]}'
    assert parse_intent(raw,{"f","r"}).match_fields==["answer"]
    with pytest.raises(ValueError):parse_intent(raw.replace('"review"','"recognition"'),{"f","r"})
    with pytest.raises(ValueError):parse_intent(raw.replace('["r"]','[]'),{"f","r"})
    item={"uid":"a","kind":"question","content":"x","title":"题","answer":"","solution":"已有"}
    assert missing_match_items([item],["answer","solution"],{})[0]["fields"]==["answer"]
    assert not missing_match_items([item],["answer"],{"a":[(item,["answer"])]})
    assert missing_match_items([{**item,"content":"y"}],["answer"],{"a":[(item,["answer"])]})

def test_null_goal_and_optional_defaults_follow_user_request():
    import json
    from app.api.work_agent import intake_goal_hint
    record={"id":"r","instruction":"把这些题目录入，这是郑州大学考研真题","amendments":[{"text":"重新识别图片"}]}
    raw=json.dumps({"action":"recognize","file_id":"f","count":9,"goal":None,"focus":None,"reference_ids":None,"match_fields":None,"explanation":None})
    intent=parse_intent(raw,{"f"},intake_goal_hint(record))
    assert intent.goal=="document" and intent.count==9 and intent.focus=="mixed"
    assert intent.reference_ids==[] and intent.match_fields==[]
    assert parse_intent(raw,{"f"}).goal=="recognition"
    assert intake_goal_hint({"id":"new","instruction":"重新识别图片"},[record])=="document"
    assert intake_goal_hint({**record,"amendments":[{"text":"只识别原文，先不要整理"}]})=="recognition"
    with pytest.raises(ValueError):parse_intent(raw.replace('"goal": null','"goal": "auto_register"'),{"f"},"document")
    with pytest.raises(ValueError):parse_intent(raw.replace('"count": 9','"count": null'),{"f"},"document")
    assert parse_intent('{"action":"clarify","goal":null,"explanation":"哪份？"}',{"f"},"document").goal=="recognition"

def test_replanning_contains_intake_contract():
    from app.core.ai_work import later_prompt
    prompt=later_prompt({"instruction":"重新识别图片","steps":[]})
    assert "goal必须是recognition、review或document" in prompt
    assert "不能为null" in prompt
