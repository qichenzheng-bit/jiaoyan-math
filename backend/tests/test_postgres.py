"""Opt-in integration test; run only against an isolated PostgreSQL database."""
import os
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from app.core.config import settings
from app.core.db import engine, session_factory
from app.core.security import hash_password, now
from app.main import create_app
from app.models import User

@pytest.mark.skipif(os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
                    reason="requires dedicated PostgreSQL test database")
def test_migration_and_login(tmp_path, monkeypatch):
    from dataclasses import replace
    from app.services import storage
    monkeypatch.setattr(storage, 'settings', replace(storage.settings, storage_root=str(tmp_path)))
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert engine().url.database == "jiaoyan_ci", "Use a dedicated CI database"
    command.upgrade(Config("alembic.ini"), "head")
    assert {"users", "sessions", "settings", "files", "audit_logs", "file_references", "teaching_resources", "chat_sessions", "chat_messages", "resource_source_links", "resource_source_versions", "knowledge_point_catalog", "resource_knowledge_links", "alembic_version"} <= set(inspect(engine()).get_table_names())
    with TestClient(create_app(), base_url="https://testserver") as client:
        assert client.get("/api/ready").status_code == 503
        assert client.get("/api/system").status_code == 401
        with session_factory()() as db:
            db.add(User(id=1, username="ci-admin", password_hash=hash_password("ci-only-password-2026"), created_at=now()))
            db.commit()
        assert client.get("/api/ready").status_code == 200
        origin = {"Origin":settings.app_origin}
        response = client.post("/api/auth/login", headers=origin, json={"username":"ci-admin", "password":"ci-only-password-2026"})
        assert response.status_code == 200
        assert client.get("/api/system").status_code == 200
        assert client.get("/api/files").status_code == 200
        upload = client.post("/api/files?name=notes.txt", headers=origin, content=b"test file")
        assert upload.status_code == 200, upload.text
        item = upload.json()
        duplicate = client.post("/api/files?name=copy.txt", headers=origin, content=b"test file")
        assert duplicate.status_code == 200 and duplicate.json()["duplicate"]
        assert duplicate.json()["id"] == item["id"]
        assert client.get("/api/files/" + item["id"] + "/download").content == b"test file"
        assert client.post("/api/files/" + item["id"] + "/archive", headers=origin).status_code == 200
        assert client.get("/api/files?archived=true").json()["total"] == 1
        assert client.post("/api/files/" + item["id"] + "/restore", headers=origin).status_code == 200
        draft={"kind":"question","title":"极限","subject":"高数","content":"求极限","solution":"方法"}
        created=client.post("/api/resources",headers=origin,json=draft)
        assert created.status_code==200,created.text
        rid=created.json()["id"]
        assert created.json()["subject"]=="高等数学"
        assert client.post("/api/resources/duplicates",headers=origin,json=draft).json()[0]["id"]==rid
        assert client.get("/api/resources?kind=question").json()["total"]==1
        assert client.post("/api/resources/"+rid+"/archive",headers=origin).status_code==200
        assert client.get("/api/resources?kind=question").json()["total"]==0
        assert client.post("/api/resources/"+rid+"/restore",headers=origin).status_code==200
        assert created.json()["code"].startswith("Q")
        assert client.post("/api/resources",headers=origin,json=draft).status_code==409
        source=client.post("/api/resources",headers=origin,json={"kind":"source","title":"教材","content":"说明","source_type":"textbook"}).json()
        assert source["code"].startswith("S")
        links=client.get("/api/resources/"+rid+"/sources").json()
        changed=client.put("/api/resources/"+rid+"/sources",headers=origin,json={"revision":links["revision"],"items":[{"source_id":source["id"],"is_primary":True,"page_start":1,"page_end":2}]})
        assert changed.status_code==200,changed.text
        assert client.get("/api/resources/"+rid).json()["source_id"]==source["id"]
        assert client.post("/api/resources/"+source["id"]+"/archive",headers=origin).status_code==409
        assert client.put("/api/resources/"+rid+"/sources",headers=origin,json={"revision":links["revision"],"items":[]}).status_code==409
        assert client.get("/api/resources/"+source["id"]+"/versions").json()[0]["version"]==1
        assert client.put("/api/resources/"+rid,headers=origin,json={**draft,"revision":1}).status_code==409
        from app.api import qoder
        monkeypatch.setattr(qoder,"available_models",lambda:{"models":[{"id":"Auto"},{"id":"Qwen4-Max"}]})
        assert client.get("/api/qoder/preferences").json()=={"model":"Auto"}
        assert client.put("/api/qoder/preferences",headers=origin,json={"model":"Qwen4-Max"}).status_code==200
        assert client.get("/api/qoder/preferences").json()=={"model":"Qwen4-Max"}
        assert client.put("/api/qoder/preferences",headers=origin,json={"model":"Unknown"}).status_code==422
        assert client.put("/api/qoder/preferences",json={"model":"Auto"}).status_code==403
        from app.api import qoder as chat_qoder
        def fake_worker(method,path,body=None):
            if path=="/status": return {"chat_available":True}
            if path=="/chat/start": return {"state":"running"}
            return {"state":"done","answer":"2","detail":""}
        monkeypatch.setattr(chat_qoder,"request",fake_worker)
        session=client.post("/api/chat/sessions",headers=origin,json={})
        assert session.status_code==200,session.text
        chat_id=session.json()["id"]
        reply=client.post("/api/chat/sessions/"+chat_id+"/turn",headers=origin,json={"content":"1+1","model":"Auto"})
        assert reply.status_code==200,reply.text
        assert reply.json()["messages"][-1]["content"]=="2"
        assert client.patch("/api/chat/sessions/"+chat_id,headers=origin,json={"pinned":True}).json()["pinned"]
        assert client.get("/api/chat/sessions").json()[0]["id"]==chat_id
        prefs = {"display_name":"微光数学测试","theme":"dark"}
        assert client.put("/api/settings",headers=origin,json=prefs).status_code == 200
        assert client.get("/api/settings").json() == prefs
        invalid = client.post("/api/auth/password", headers=origin, json={"current_password":"do-not-echo-this","new_password":"short"})
        assert invalid.status_code == 422 and "do-not-echo-this" not in invalid.text
        assert client.post("/api/auth/logout", headers=origin).status_code == 200
        assert client.get("/api/system").status_code == 401
        assert client.get("/api/files").status_code == 401
        assert client.get("/api/files/" + item["id"] + "/download").status_code == 401
    command.check(Config("alembic.ini"))
