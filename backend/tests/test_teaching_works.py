"""Isolated registry tests; no production database or storage."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from dataclasses import replace

from app.models import User, StoredFile, FileReference, AuditLog, TeachingWork, TeachingWorkVersion, TeachingWorkAsset, TeachingWorkPendingCover
from app.services import storage, teaching_works


def test_pdf_registration_keeps_two_versions_and_original_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "settings", replace(storage.settings, storage_root=str(tmp_path)))
    engine = create_engine("sqlite://")
    for model in (User, StoredFile, FileReference, AuditLog, TeachingWork, TeachingWorkVersion, TeachingWorkAsset, TeachingWorkPendingCover):
        model.__table__.create(engine)
    path = tmp_path / "queue.pdf"
    with Session(engine) as db:
        db.add(User(id=1, username="test", password_hash="test", created_at=1))
        db.commit()
        def register(content):
            path.unlink(missing_ok=True)
            path.write_bytes(("%PDF-1.7\n" + content).encode())
            payload = {"doc": {"title": "讲义", "kind": "handout", "blocks": [{"content": content}]},
                       "layout": {"paper": "A4"}}
            result = teaching_works.register_pdf(db, user_id=1, scope="doc", identity="doc-1",
                                                  filename="test.pdf", path=path, payload=payload, pages=1)
            db.commit()
            return result
        first = register("one")
        assert register("one") == first
        assert register("two") == (first[0], 2)
        assert register("three") == (first[0], 3)
        assert list(db.scalars(select(TeachingWorkVersion.number).order_by(TeachingWorkVersion.number))) == [2, 3]
        assert len(list(db.scalars(select(TeachingWorkAsset)))) == 2
        assert len(list(db.scalars(select(FileReference)))) == 2
        current = db.get(TeachingWorkAsset, (first[0], 3, "body"))
        f = db.get(StoredFile, current.file_id)
        path.unlink()
        assert storage.file_path(f).read_bytes() == b"%PDF-1.7\nthree"


def test_cover_first_and_mismatch_do_not_replace_body(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "settings", replace(storage.settings, storage_root=str(tmp_path)))
    engine = create_engine("sqlite://")
    for model in (User, StoredFile, FileReference, AuditLog, TeachingWork, TeachingWorkVersion,
                  TeachingWorkAsset, TeachingWorkPendingCover):
        model.__table__.create(engine)
    with Session(engine) as db:
        db.add(User(id=1, username="test", password_hash="test", created_at=1))
        db.commit()
        def register(content, cover=False):
            path = tmp_path / ("render-" + content + ("-cover" if cover else "") + ".pdf")
            path.unlink(missing_ok=True)
            path.write_bytes(("%PDF-1.7\n" + content + str(cover)).encode())
            payload = {"doc":{"title":"教材","kind":"textbook","blocks":[{"content":content}]},
                       "layout":{"paper":"A4"}, "wrap":{"spine":8} if cover else None}
            payload["work_context"] = teaching_works.context(payload)
            result = teaching_works.register_pdf(db,user_id=1,scope="doc",identity="book",
                    filename="cover.pdf" if cover else "body.pdf",path=path,payload=payload,pages=1)
            db.commit()
            return result
        wid, ver = register("A", True)
        assert ver == 0
        assert register("A") == (wid, 1)
        assert db.get(TeachingWorkAsset,(wid,1,"cover"))
        assert register("B", True) == (wid, 0)
        assert db.get(TeachingWork,wid).current_version == 1
        assert register("B") == (wid, 2)
        assert db.get(TeachingWorkAsset,(wid,2,"cover"))
        assert db.get(TeachingWorkPendingCover,wid) is None
        assert register("C") == (wid, 3)
        assert db.get(TeachingWorkAsset,(wid,3,"cover")) is None
        old = list(db.scalars(select(StoredFile).where(StoredFile.work_managed == True)))
        teaching_works.retire_files(db)
        retired = [f for f in old if f.work_retired_at is not None]
        assert len(retired) == 2
        monkeypatch.setattr(teaching_works,"now",lambda: max(f.work_retired_at for f in retired)+3601)
        assert teaching_works.retire_files(db) == 2
        assert all(f.purged_at is not None for f in retired)
        assert all(not (tmp_path/f.storage_key).exists() for f in retired)


def test_restore_reuses_bytes_and_does_not_change_original(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "settings", replace(storage.settings, storage_root=str(tmp_path)))
    engine = create_engine("sqlite://")
    for model in (User, StoredFile, FileReference, AuditLog, TeachingWork, TeachingWorkVersion,
                  TeachingWorkAsset, TeachingWorkPendingCover):
        model.__table__.create(engine)
    with Session(engine) as db:
        db.add(User(id=1,username="test",password_hash="test",created_at=1))
        db.commit()
        for text in ("old","new"):
            path=tmp_path/(text+".pdf")
            path.write_bytes(("%PDF-1.7\n"+text).encode())
            wid,_=teaching_works.register_pdf(db,user_id=1,scope="doc",identity="doc",
                filename="work.pdf",path=path,payload={"doc":{"title":"讲义","blocks":[{"content":text}]},"layout":{}},pages=1)
            db.commit()
        original=db.get(TeachingWorkAsset,(wid,1,"body")).file_id
        assert teaching_works.restore_version(db,user_id=1,work_id=wid,number=1,expected=2)==(wid,3)
        db.commit()
        assert db.get(TeachingWorkAsset,(wid,3,"body")).file_id==original
        assert db.get(TeachingWorkVersion,(wid,3)).snapshot["restored_from"]==1
        assert db.get(TeachingWorkVersion,(wid,1)) is None
        assert len(list(db.scalars(select(StoredFile))))==2
        import pytest
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as err:
            teaching_works.restore_version(db,user_id=1,work_id=wid,number=2,expected=2)
        assert err.value.status_code==409
