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
