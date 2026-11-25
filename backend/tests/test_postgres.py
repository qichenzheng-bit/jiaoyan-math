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
    assert {"users", "sessions", "settings", "files", "audit_logs", "file_references", "alembic_version"} <= set(inspect(engine()).get_table_names())
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
