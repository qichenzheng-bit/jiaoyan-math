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
