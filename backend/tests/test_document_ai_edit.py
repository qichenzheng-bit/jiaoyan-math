
import json
import pytest
from app.api.documents import parse_edit_changes

def test_scoped_patches_and_noop():
    blocks=[{"uid":"q1","kind":"question","title":"极限","content":"求极限","solution":"旧解析"},{"uid":"r1","kind":"reference","content":"引用"}]
    assert parse_edit_changes("[]",blocks,["solution"])==[]
    result=parse_edit_changes(json.dumps([{"uid":"q1","field":"solution","value":"新解析"}]),blocks,["solution"])
    assert result==[{"uid":"q1","field":"solution","before":"旧解析","after":"新解析"}]
    for patch in [
        {"uid":"q2","field":"solution","value":"新解析"},
        {"uid":"q1","field":"content","value":"改题"},
        {"uid":"r1","field":"solution","value":"改引用"},
        {"uid":"q1","field":"solution","value":1},
        {"uid":"q1","field":"solution","value":"新解析","kind":"reference"}]:
        with pytest.raises(ValueError):parse_edit_changes(json.dumps([patch]),blocks,["solution"])
    with pytest.raises(ValueError):parse_edit_changes(json.dumps([{"uid":"q1","field":"solution","value":"甲"},{"uid":"q1","field":"solution","value":"乙"}]),blocks,["solution"])
