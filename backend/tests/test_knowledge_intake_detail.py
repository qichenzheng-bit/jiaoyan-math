import json
from types import SimpleNamespace
from unittest.mock import Mock

from app.api import documents, intelligence, resources
from app.services.knowledge_video_source import build_snapshot
from test_knowledge_video_source import unit


def test_source_detail_survives_ai_parse_and_review():
    raw={"kind":"knowledge","title":"定义","content":"完整正文","proof":"",
         "teaching_detail":{"conditions":"原文条件","applications":"实际应用"}}
    item=intelligence.parse_answer(json.dumps([raw],ensure_ascii=False))[0]
    saved=documents.Block.model_validate(item).model_dump()
    assert saved["proof"]==""
    assert saved["teaching_detail"]=={"conditions":"原文条件","applications":"实际应用","methods":"","mistakes":""}
    db=Mock()
    resources.save_initial_unit_detail(db,unit(),saved["teaching_detail"])
    setting=db.add.call_args.args[0]
    assert setting.key==resources.unit_detail_key("u")
    detail=json.loads(setting.value)
    assert detail["example_ids"]==[]
    data=build_snapshot(unit(),detail,[])
    assert data["teaching_detail"]["conditions"]=="原文条件"
    assert data["association_count"]==0


def test_legacy_blocks_and_empty_detail_remain_compatible():
    item=documents.Block(uid="u",kind="knowledge",title="定义",content="正文")
    assert item.teaching_detail is None
    db=Mock()
    resources.save_initial_unit_detail(db,unit(),documents.KnowledgeTeachingDraft().model_dump())
    db.add.assert_not_called()
