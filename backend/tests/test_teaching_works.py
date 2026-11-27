"""Isolated registry tests; no production database or storage."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from dataclasses import replace

from app.models import User, StoredFile, FileReference, AuditLog, TeachingWork, TeachingWorkVersion, TeachingWorkAsset
from app.services import storage, teaching_works


def test_pdf_registration_keeps_two_versions_and_original_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "settings", replace(storage.settings, storage_root=str(tmp_path)))
    engine = create_engine("sqlite://")
    for model in (User, StoredFile, FileReference, AuditLog, TeachingWork, TeachingWorkVersion, TeachingWorkAsset):
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
