from types import SimpleNamespace
from app.api.documents import assemble_source_export

def test_source_export_preserves_batches_and_avoids_duplicate_links(monkeypatch):
    from app.api import documents
    monkeypatch.setattr(documents.bank,"view",lambda r:{"id":r.id,"kind":"question","title":r.id,"content":"已入库正文"})
    src=SimpleNamespace(title="来源试卷",subject="高等数学",source_type="exam",content="登记信息")
    rows=[SimpleNamespace(id="q1"),SimpleNamespace(id="q2"),SimpleNamespace(id="q2")]
    docs=[SimpleNamespace(id="batch1",title="第一批",blocks=[{"uid":"original","kind":"reference","resource_id":"q1","snapshot":{"content":"原快照"}}]),SimpleNamespace(id="batch2",title="第二批",blocks=[{"uid":"original","kind":"text","content":"原文"}])]
    result=assemble_source_export(src,docs,rows)
    assert result["kind"]=="paper" and result["batch_count"]==2
    assert [b["kind"] for b in result["blocks"]]==["heading","reference","heading","text","heading","reference"]
    assert result["blocks"][1]["snapshot"]["content"]=="原快照"
    assert result["blocks"][-1]["resource_id"]=="q2"
    assert len({b["uid"] for b in result["blocks"]})==6

def test_empty_source_does_not_claim_complete_content():
    src=SimpleNamespace(title="教材",subject="高等数学",source_type="textbook",content="登记信息")
    result=assemble_source_export(src,[],[])
    assert result["has_source_content"] is False
    assert result["blocks"][0]["content"]=="登记信息"


def test_pending_source_batch_is_not_exported():
    src=SimpleNamespace(title="来源",subject="高等数学",source_type="exam",content="登记")
    draft=SimpleNamespace(id="draft",title="草稿",blocks=[{"uid":"q","kind":"question","content":"未入库"}])
    result=assemble_source_export(src,[draft],[])
    assert not result["has_source_content"]
    assert all(b.get("content")!="未入库" for b in result["blocks"])
