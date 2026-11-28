import pytest
from app.api.work_agent import Intent, missing_match_items

def test_historical_plan_schema_still_validates_business_data():
    assert Intent.model_validate({"action":"recognize","file_id":"f","count":5}).count==5
    for data in [{"action":"delete","file_id":"f"},{"action":"recognize","file_id":"f","count":11},{"action":"recognize","file_id":"f","count":"5"},{"action":"review","file_id":"f"},{"action":"attach","file_id":"f","shell":"rm"},{"action":"recognize","file_id":"f","count":5,"goal":"auto_register"}]:
        with pytest.raises(ValueError):Intent.model_validate(data)
    assert Intent.model_validate({"action":"clarify","explanation":"哪一本？"}).action=="clarify"

def test_historical_reference_match_business_guard():
    raw={"action":"recognize","file_id":"f","count":5,"goal":"review","reference_ids":["r"],"match_fields":["answer"]}
    assert Intent.model_validate(raw).match_fields==["answer"]
    with pytest.raises(ValueError):Intent.model_validate({**raw,"goal":"recognition"})
    with pytest.raises(ValueError):Intent.model_validate({**raw,"reference_ids":[]})
    item={"uid":"a","kind":"question","content":"x","title":"题","answer":"","solution":"已有"}
    assert missing_match_items([item],["answer","solution"],{})[0]["fields"]==["answer"]
    assert not missing_match_items([item],["answer"],{"a":[(item,["answer"])]})
    assert missing_match_items([{**item,"content":"y"}],["answer"],{"a":[(item,["answer"])]})
