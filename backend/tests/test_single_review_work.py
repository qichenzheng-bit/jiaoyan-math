"""Single review drafts must not manufacture human verification."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from app.api import workspaces as w, work_agent as wa

def test_complete_machine_transcription_enters_draft_without_verification(monkeypatch):
    session=SimpleNamespace(id="workspace",updated_at=0)
    batch=SimpleNamespace(id="batch",job_id=None,verified_text=None,import_id=None,material_id="material",start=1,end=1,units=[{"unit":1,"state":"done","text":"原题 $x^2$","warnings":["待核对"]}])
    material=SimpleNamespace(id="material",session_id="workspace",file_id="file",total_units=1)
    original=SimpleNamespace(id="file",name="exam.jpg",media_type="image/jpeg",sha256="a"*64)
    db=Mock();db.get.return_value=material
    monkeypatch.setattr(w,"workspace",lambda *a:session)
    monkeypatch.setattr(w,"batch",lambda *a:batch)
    monkeypatch.setattr(w,"file_for",lambda *a:original)
    launch=Mock(return_value={"id":"job","state":"running"})
    monkeypatch.setattr(w.ai,"launch",launch)
    result=w.organize_unverified("workspace","batch",w.Organize(),db,object())
    assert result["state"]=="running"
    args=launch.call_args.args
    assert args[3]["single_review"] is True
    assert args[3]["import_reviewed"] is False
    assert args[3]["reviewed_uids"]==[]
    assert args[2].text.endswith("原题 $x^2$")
    assert batch.verified_text is None
    batch.units[0]["state"]="failed"
    with pytest.raises(HTTPException) as exc:w.organize_unverified("workspace","batch",w.Organize(),db,object())
    assert exc.value.status_code==409

def test_auto_review_policy_preserves_explicit_raw_review(monkeypatch):
    db=Mock()
    s=SimpleNamespace(id="w")
    m=SimpleNamespace(id="m",session_id="w",file_id="f")
    b=SimpleNamespace(id="b",material_id="m",start=1,end=1,units=[{"unit":1,"state":"done"}],verified_text=None)
    from app.models import WorkMaterial, WorkBatch, StoredFile
    db.get.side_effect=lambda model,id:{WorkMaterial:m,WorkBatch:b,StoredFile:SimpleNamespace(archived=False)}[model]
    monkeypatch.setattr(w,"latest_job",lambda *a:None)
    r={"state":"dispatched","auto":True,"single_review":True,"plan":{"goal":"document"},"result":{"material_id":"m","batch_id":"b"}}
    assert wa.workflow(db,s,r)["stage"]=="organize"
    r["plan"]["goal"]="recognition"
    assert wa.workflow(db,s,r)["stage"]=="verify"
    r["plan"]["goal"]="document";r["single_review"]=False
    assert wa.workflow(db,s,r)["stage"]=="verify"
    assert w.reviewed_batch(SimpleNamespace(state="review",provenance={"single_review":True})) is False
    assert w.reviewed_batch(SimpleNamespace(state="converted",provenance={"single_review":True})) is True


def test_direct_registration_refuses_unapproved_before_source_write(monkeypatch):
    from app.api import intelligence as ai
    from fastapi import HTTPException
    import pytest
    from types import SimpleNamespace
    monkeypatch.setattr(ai.bank,"admin_lock",lambda *a:None)
    monkeypatch.setattr(ai,"get_job",lambda *a:SimpleNamespace(state="review",document_id=None,revision=1,items=[{"uid":"x"}],provenance={"reviewed_uids":[]}))
    with pytest.raises(HTTPException,match="逐题核对"):
        ai.direct_register("job",ai.DirectIntake(revision=1,title="试卷"),None,None)
