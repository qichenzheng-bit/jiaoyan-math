import pytest
from app.api.intelligence import parse_answer
def test_extraction():
    rows=parse_answer('[{"kind":"question","title":"极限","content":"求极限"}]')
    assert rows[0]["kind"]=="question" and rows[0]["answer"]==""
    with pytest.raises(ValueError):
        parse_answer('[{"kind":"reference","title":"x","content":"x"}]')

from app.api.chat import split_intake_intent

def test_intent_protocol_is_exact_and_not_an_action():
    assert split_intake_intent("请确认录入。\n[[WG_INTAKE:question]]")==("请确认录入。","question")
    for text in ("普通答疑","[[WG_INTAKE:question]]","正文\n[[WG_INTAKE:delete]]","正文\n[[WG_INTAKE:question]]\n后文"):
        assert split_intake_intent(text)==(text,None)

from app.api.intelligence import parse_supplement,apply_supplement,allowed_supplements
from fastapi import HTTPException

def test_supplement_only_fills_missing_or_appends():
    item=parse_answer('[{"kind":"question","title":"求导","content":"求导数","answer":"2x","solution":"原解法"}]')[0]
    assert allowed_supplements(item)==["analysis","alternate"]
    with pytest.raises(ValueError):parse_supplement('{"content":"改题干"}',["analysis"])
    with pytest.raises(HTTPException):apply_supplement(item,{"answer":"其他"},["answer"])
    with pytest.raises(HTTPException):apply_supplement(item,{"alternate":"原解法"},["alternate"])
    result=apply_supplement(item,{"alternate":"另一解法","analysis":"思路"},["alternate","analysis"])
    assert result["content"]==item["content"] and result["answer"]==item["answer"]
    assert "原解法" in result["solution"] and "另一解法" in result["solution"]
    assert result["analysis"]=="思路"


def test_explicit_targeted_revision_does_not_change_other_fields():
    item={"uid":"q1","kind":"question","title":"原题","content":"原文","answer":"旧答案","solution":"原解析"}
    result=apply_supplement(item,{"answer":"新答案"},["answer"],revise=True)
    assert result["answer"]=="新答案" and result["content"]=="原文" and result["solution"]=="原解析"
    with pytest.raises(HTTPException):apply_supplement(item,{"answer":"新答案"},["answer"])
    with pytest.raises(HTTPException):apply_supplement(item,{"proof":"证明"},["proof"],revise=True)


def test_duplicate_decision_uses_manual_matcher(monkeypatch):
    from app.api import intelligence
    from types import SimpleNamespace
    item=parse_answer('[{"kind":"question","title":"求导","content":"求导数"}]')[0]
    calls=[]
    def matches(body,db):
        calls.append((body.kind,body.content))
        return {"total":1}
    monkeypatch.setattr(intelligence.docs,"manual_matches",matches)
    with pytest.raises(HTTPException) as exc:
        intelligence.verify_duplicate_choice(None,item,"")
    assert exc.value.status_code==409 and calls==[("question","求导数")]
    intelligence.verify_duplicate_choice(None,{**item,"dedup_reason":"条件不同"},"")
    assert len(calls)==1
    resource=SimpleNamespace(**{**item,"archived":False,"revision":2,"subject":"","difficulty":""})
    monkeypatch.setattr(intelligence.bank,"existing",lambda db,ident:resource)
    reused={**item,"reuse_resource_id":"old","reuse_revision":2,"subject":""}
    intelligence.verify_duplicate_choice(None,reused,"")
    with pytest.raises(HTTPException):intelligence.verify_duplicate_choice(None,{**reused,"reuse_revision":1},"")
    with pytest.raises(HTTPException):intelligence.verify_duplicate_choice(None,{**reused,"content":"修改后的题干"},"")
