import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.models import User, WorkSession, WorkMaterial, WorkBatch, StoredFile, FileReference, IntakeJob, IntakeImport, IntakeSupplement, TeachingDocument, TeachingResource
from app.services import work_removal as removal

def test_remove_workspace_preserves_shared_original_and_document():
    engine=create_engine("sqlite://")
    @event.listens_for(engine,"connect")
    def foreign_keys(conn,_):conn.execute("PRAGMA foreign_keys=ON")
    for model in (User,StoredFile,TeachingResource,TeachingDocument,IntakeImport,IntakeJob,IntakeSupplement,WorkSession,WorkMaterial,WorkBatch,FileReference):
        model.__table__.create(engine)
    with Session(engine) as db:
        db.add(User(id=1,username="test",password_hash="x",created_at=1))
        db.add(StoredFile(id="f",name="test.pdf",media_type="application/pdf",size_bytes=1,sha256="a"*64,storage_key="f",created_at=1,archived=False,generated=False))
        db.add(StoredFile(id="g",name="private.pdf",media_type="application/pdf",size_bytes=1,sha256="b"*64,storage_key="g",created_at=1,archived=False,generated=False))
        db.add_all([WorkSession(id="w",title="delete",created_at=1,updated_at=1),WorkSession(id="other",title="keep",created_at=1,updated_at=1)])
        db.flush()
        db.add_all([WorkMaterial(id="m",session_id="w",file_id="f",total_units=2,created_at=1),WorkMaterial(id="m2",session_id="other",file_id="f",total_units=2,created_at=1),WorkMaterial(id="m3",session_id="w",file_id="g",total_units=2,created_at=1)])
        db.add(TeachingDocument(id="d",title="doc",kind="intake",subject="",blocks=[],revision=1,archived=False,created_at=1,updated_at=1))
        db.flush()
        def job(ident,state,document=None):
            return IntakeJob(id=ident,title="work",subject="",input_text="text",provenance={"workspace_id":"w"},model="Auto",state=state,detail="",items=[],document_id=document,revision=1,created_at=1,updated_at=1)
        db.add_all([job("draft","review"),job("converted","converted","d")]);db.flush()
        db.add_all([WorkBatch(id="b",material_id="m",start=1,end=1,units=[],created_at=1,updated_at=1),WorkBatch(id="b2",material_id="m3",start=1,end=1,units=[],job_id="draft",created_at=1,updated_at=1)])
        db.add(FileReference(file_id="f",owner_type="work_material",owner_id="m"))
        db.commit()
        assert set(removal.remove_workspace(db,db.get(WorkSession,"w")))=={"draft","converted"}
        db.commit()
        assert db.get(WorkSession,"w") is None and db.get(WorkMaterial,"m") is None
        assert db.get(WorkBatch,"b").material_id=="m2" and db.get(StoredFile,"f") is not None
        assert db.get(WorkBatch,"b2") is None and db.get(IntakeJob,"draft") is None
        assert db.get(TeachingDocument,"d") is not None and db.get(IntakeJob,"converted").provenance["history_removed"]
        from app.api import intelligence
        assert intelligence.listing(db)==[]

def test_running_task_must_stop_before_removal(monkeypatch):
    calls=[]
    def request(method,path,body=None):
        calls.append(method)
        return {"state":"running"}
    monkeypatch.setattr(removal.qoder,"request",request)
    with pytest.raises(HTTPException) as exc:removal.stop_model("active",0)
    assert exc.value.status_code==409 and calls==["GET","POST","GET"]
