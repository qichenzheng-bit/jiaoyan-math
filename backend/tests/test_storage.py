from dataclasses import replace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.db import Base
from app.models import User
from app.services import storage

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "settings", replace(storage.settings, storage_root=str(tmp_path)))
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add(User(id=1, username="admin", password_hash="unused", created_at=1))
        session.commit()
        yield session
    engine.dispose()

def stage(content):
    path = storage.new_stage()
    path.write_bytes(content)
    return path

def test_upload_deduplicate_reference(db):
    first = storage.save_staged(db, stage(b"hello"), "notes.txt", 1)
    second_path = stage(b"hello")
    try:
        second = storage.save_staged(db, second_path, "copy.txt", 1)
    finally:
        second_path.unlink(missing_ok=True)
    assert second["duplicate"] and first["id"] == second["id"]
    storage.link_file(db, first["id"], "resource", "r1")
    db.commit()
    assert storage.reference_count(db, first["id"]) == 1

def test_reject_disguised_executable(db):
    temp = stage(b"<script>alert(1)</script>")
    try:
        with pytest.raises(HTTPException) as exc:
            storage.save_staged(db, temp, "bad.png", 1)
        assert exc.value.status_code == 415
    finally:
        temp.unlink(missing_ok=True)

def test_separate_generated_storage(db):
    a = storage.save_staged(db, stage(b"test"), "a.txt", 1)
    b = storage.save_staged(db, stage(b"test"), "a.txt", 1, generated=True)
    assert a["id"] != b["id"] and b["generated"]

def test_inline_image_tokens_are_validated_and_size_is_not_identity(db):
    import base64
    from app.services.inline_images import validate_images,image_ids
    from app.core.content_normalization import question_fingerprint
    png=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/b1sAAAAASUVORK5CYII=")
    stored=storage.save_staged(db,stage(png),"diagram.png",1)
    marker=lambda size:"[[img:"+stored["id"]+":"+str(size)+"]]"
    assert validate_images(db,{"content":"图 "+marker(50)})=={stored["id"]}
    assert image_ids({"content":marker(25),"snapshot":{"content":marker(75)}})=={stored["id"]}
    assert question_fingerprint("图 "+marker(25),"","")==question_fingerprint("图 "+marker(75),"","")
    with pytest.raises(HTTPException):
        validate_images(db,{"content":"[[img:00000000-0000-0000-0000-000000000000:50]]"})


def test_purge_refuses_unsafe_path_and_preserves_tombstone(db):
    from app.models import StoredFile
    first=storage.save_staged(db,stage(b"purge content"),"purge.txt",1)
    item=db.get(StoredFile,first["id"])
    path=storage.file_path(item)
    with pytest.raises(ValueError):storage.remove_purged_original(item)
    item.archived=True;item.purged_at=1;item.purge_pending=True;db.commit()
    with pytest.raises(HTTPException) as exc:storage.file_path(item)
    assert exc.value.status_code==410
    storage.remove_purged_original(item)
    storage.remove_purged_original(item)
    assert not path.exists()
    new=storage.save_staged(db,stage(b"purge content"),"purge.txt",1)
    assert new["id"]!=item.id and not new["duplicate"]
