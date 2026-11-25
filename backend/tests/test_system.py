from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import settings

client = TestClient(create_app())

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": settings.version}

def test_no_public_api_docs():
    assert client.get("/docs").status_code == 404

def test_business_api_requires_login():
    # Phase 02 exposes resource routes only to authenticated administrators.
    for path in ("/api/resources", "/api/resources/subjects", "/api/qoder/status"):
        assert client.get(path).status_code == 401
    assert client.post("/api/qoder/test", json={"model": "Auto", "prompt": "test"}).status_code == 401

def test_qoder_login_requires_admin():
    for action in ("start", "cancel"):
        assert client.post("/api/qoder/login/"+action).status_code == 401

def test_model_config_is_private():
    assert client.get("/api/qoder/models").status_code==401
    assert client.get("/api/qoder/preferences").status_code==401
    assert client.post("/api/qoder/models/refresh").status_code==401

def test_chat_is_private():
    assert client.get("/api/chat/sessions").status_code==401
    assert client.post("/api/chat/sessions",json={}).status_code==401

def test_resource_detail_is_private():
    assert client.get("/api/resources/example").status_code==401
    assert client.get("/api/resources/example/sources").status_code==401
    assert client.get("/api/resources/example/versions").status_code==401

def test_knowledge_private():
    assert client.get("/api/knowledge/points").status_code==401
    assert client.get("/api/knowledge/relations").status_code==401
