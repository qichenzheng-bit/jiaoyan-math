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


def test_pdf_location_hints_are_bounded_and_untrusted():
    from app.api.intelligence import pdf_range,valid_pages
    hints={}
    rows=parse_answer('[{"kind":"question","title":"题目","content":"求极限","source_pages":{"content":4,"answer":9,"solution":"4","proof":true,"unknown":3}}]',hints,(3,5))
    assert hints=={rows[0]["uid"]:{"content":4}}
    assert "source_pages" not in rows[0]
    assert pdf_range({"file_media_type":"application/pdf","work_batch_id":"b","start":1,"end":10})==(1,10)
    assert pdf_range({"file_media_type":"application/pdf","work_batch_id":"b","start":1,"end":11}) is None
    with pytest.raises(HTTPException):valid_pages({"answer":8},(3,5),True)


def test_source_matching_only_accepts_exact_excerpts():
    from app.api.intelligence import literal_source_proposal,source_page
    from types import SimpleNamespace
    assert literal_source_proposal('{"answer":"答案为1"}',["answer"],"第一题：答案为1\n第二题") == {"answer":"答案为1"}
    with pytest.raises(ValueError):literal_source_proposal('{"answer":"答案为2"}',["answer"],"第一题：答案为1")
    b=SimpleNamespace(units=[{"unit":2,"state":"done","text":"答案为1"},{"unit":3,"state":"done","text":"答案为2"}])
    assert source_page("答案为1",b)==2
    b.units[1]["text"]="答案为1"
    assert source_page("答案为1",b) is None


def test_batch_reference_proposals_are_independent():
    from app.api.intelligence import batch_match_targets,parse_batch_source
    items=[{"uid":"a","kind":"question","answer":"","solution":"已有解析"},{"uid":"b","kind":"question","answer":"","solution":""}]
    targets=batch_match_targets(items,["a","b"],["answer","solution"])
    assert [t["fields"] for t in targets]==[["answer"],["answer","solution"]]
    result=parse_batch_source('{"a":{"answer":"原答案1"},"b":{"answer":"不存在"}}',targets,"第一题 原答案1")
    assert result=={"a":{"answer":"原答案1"},"b":{}}
    with pytest.raises(ValueError):parse_batch_source('{"c":{"answer":"原答案1"}}',targets,"原答案1")
    with pytest.raises(HTTPException):batch_match_targets(items,["a","a"],["answer"])


def test_coverage_checks_explicit_exam_labels_and_unreadable_stems():
    import pytest
    from app.api.intelligence import validate_question_coverage
    items=[{"kind":"question","title":"第一问","original_question_number":"1","content":"求极限"}]
    with pytest.raises(ValueError,match="遗漏题号"):validate_question_coverage("第1题：极限\n第2题：积分",items)
    with pytest.raises(ValueError,match="未识别"):validate_question_coverage("普通题目",[{**items[0],"content":"【无法辨认】"}])
    validate_question_coverage("第1题：极限\n解：\n1. 代入",items)


def test_coverage_accepts_explicit_dotted_title():
    from app.api.intelligence import validate_question_coverage
    validate_question_coverage("习题29.1 求极限",[{"kind":"question","title":"29.1 求极限","content":"求极限"}])
