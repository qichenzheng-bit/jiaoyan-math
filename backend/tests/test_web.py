from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import web

def test_spa_preserves_api_404(tmp_path,monkeypatch):
    dist=tmp_path/"frontend"/"dist"
    (dist/"assets").mkdir(parents=True)
    (dist/"index.html").write_text("<h1>test app</h1>")
    fake=tmp_path/"backend"/"app"/"web.py"
    monkeypatch.setattr(web,"__file__",str(fake))
    app=FastAPI()
    web.mount_web(app)
    with TestClient(app) as client:
        assert client.get("/settings").status_code==200
        assert "test app" in client.get("/").text
        assert client.get("/api/unknown").status_code==404
        assert client.get("/assets/missing.js").status_code==404
