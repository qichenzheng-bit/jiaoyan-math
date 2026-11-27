from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from app.api.intelligence import tag_draft,validate_review_tags

def test_tag_draft_only_reuses_exact_subject_matches():
    db=Mock()
    db.scalar.side_effect=[SimpleNamespace(name="函数极限",status="active"),None]
    db.scalars.return_value=[]
    item={"kind":"question","subject":"数学分析","knowledge_tags":["函数极限","泰勒公式"],"primary_knowledge_tag":"函数极限","analysis":"旧思路"}
    result=tag_draft(db,item)
    assert result["knowledge_tags"]==["函数极限","泰勒公式"]
    assert result["primary_knowledge_tag"]=="函数极限" and result["analysis"]==""
    db.add.assert_not_called()
    validate_review_tags(result)

def test_primary_and_count_required():
    with pytest.raises(HTTPException):validate_review_tags({"kind":"question","knowledge_tags":["极限"]})
    with pytest.raises(HTTPException):validate_review_tags({"kind":"question","knowledge_tags":["极限","连续"],"primary_knowledge_tag":"积分"})

def test_catalog_hint_is_bounded_and_uses_real_names():
    from app.api.intelligence import catalog_hint
    db=Mock()
    db.execute.return_value=[("数学分析","函数极限"),("数学分析","连续函数")]
    assert "函数极限" in catalog_hint(db,"数学分析")
    assert "连续函数" not in catalog_hint(db,"数学分析",budget=30)

def test_existing_enrichment_preserves_reviewed_and_original_fields(monkeypatch):
    import json
    from app.api import intelligence as ai
    from app.api.documents import Block
    first=Block(uid="q1",kind="question",title="极限",content="求极限",answer="原答案",subject="数学分析").model_dump()
    second=Block(uid="q2",kind="question",title="已核对",content="已核对题干").model_dump()
    j=SimpleNamespace(provenance={"enrichment_job_id":"remote","enrichment_started_at":0,"reviewed_uids":["q2"]},items=[first,second],state="running",detail="",revision=1,updated_at=0)
    db=Mock()
    monkeypatch.setattr(ai.qoder,"request",lambda *a:{"state":"done","answer":json.dumps([{"uid":"q1","answer":"不能替换","solution":"新解析","knowledge_tags":["函数极限","连续函数"],"primary_knowledge_tag":"函数极限"},{"uid":"q2","answer":"不能修改"}])})
    monkeypatch.setattr(ai,"tag_draft",lambda db,item:item)
    ai.sync_existing_enrichment(db,j)
    assert j.state=="review" and j.items[0]["answer"]=="原答案" and j.items[0]["solution"]=="新解析"
    assert j.items[0]["generated_fields"]==["solution"]
    assert j.items[1]==second and j.provenance["reviewed_uids"]==["q2"]
