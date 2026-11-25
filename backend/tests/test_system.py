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

def test_business_api_not_exposed():
    assert client.get("/api/resources").status_code == 404
