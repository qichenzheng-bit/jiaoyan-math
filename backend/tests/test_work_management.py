"""Management tests with isolated files and SQLite; never contact video engine."""
from dataclasses import replace
from pathlib import Path
import zipfile
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models import (User, StoredFile, FileReference, AuditLog, TeachingWork,
    TeachingWorkVersion, TeachingWorkAsset, TeachingWorkPendingCover)
from app.api import teaching_works as api
from app.services import teaching_works, storage


def test_shared_file_reference_survives_version_trim_and_work_delete(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,"settings",replace(storage.settings,storage_root=str(tmp_path)))
    engine=create_engine("sqlite://")
    for model in (User,StoredFile,FileReference,AuditLog,TeachingWork,TeachingWorkVersion,
                  TeachingWorkAsset,TeachingWorkPendingCover):
        model.__table__.create(engine)
    with Session(engine) as db:
        db.add(User(id=1,username="test",password_hash="test",created_at=1));db.commit()
        user=db.get(User,1)
        def register(text):
            path=tmp_path/(text+".pdf")
            path.write_bytes(("%PDF-1.7\n"+text).encode())
            result=teaching_works.register_pdf(db,user_id=1,scope="doc",identity="doc",
                filename="body.pdf",path=path,payload={"doc":{"title":"教材","kind":"textbook",
                "blocks":[{"content":text}]},"layout":{}},pages=1)
            db.commit()
            return result
        wid,_=register("old")
        file_id=db.get(TeachingWorkAsset,(wid,1,"body")).file_id
        storage.link_file(db,file_id,"studio_item","shared-file")
        db.commit()
        register("new")
        register("latest")
        assert db.get(TeachingWorkVersion,(wid,1)) is None
        assert db.get(FileReference,(file_id,"studio_item","shared-file")) is not None
        teaching_works.retire_files(db)
        assert db.get(StoredFile,file_id).work_retired_at is None
        assert storage.file_path(db.get(StoredFile,file_id)).read_bytes()==b"%PDF-1.7\nold"
        body=api.Choices(items=[api.WorkChoice(id=wid,version=3)])
        with pytest.raises(HTTPException) as exc:api.delete_works(api.Choices(items=[api.WorkChoice(id=wid,version=2)]),db,user)
        assert exc.value.status_code==409
        db.rollback()
        work=db.get(TeachingWork,wid)
        api.rename(wid,api.RenameRequest(title="新名称",expected_updated=work.updated_at),db,user)
        assert db.get(TeachingWork,wid).current_version==3
        response=api.download_zip(body,db,user)
        with zipfile.ZipFile(response.path) as archive:
            assert len(archive.namelist())==1
            assert archive.read(archive.namelist()[0])==b"%PDF-1.7\nlatest"
        response.background.func(*response.background.args,**response.background.kwargs)
        assert not Path(response.path).exists()
        assert api.delete_works(body,db,user)["removed"]==1
        assert db.get(TeachingWork,wid) is None
        assert db.get(FileReference,(file_id,"studio_item","shared-file")) is not None
        teaching_works.retire_files(db)
        assert storage.file_path(db.get(StoredFile,file_id)).exists()
        db.delete(db.get(FileReference,(file_id,"studio_item","shared-file")))
        db.commit()
        assert not list(db.scalars(select(FileReference)))
        assert (tmp_path/"old.pdf").exists()
