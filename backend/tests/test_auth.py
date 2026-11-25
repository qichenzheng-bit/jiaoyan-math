import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.core.db import Base, get_db
from app.core.security import hash_password, now
from app.main import create_app
from app.models import User, LoginSession

ORIGIN = {"Origin": settings.app_origin}
PASSWORD = "test-password-1234"

@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, username="admin", password_hash=hash_password(PASSWORD), created_at=now()))
        db.commit()
    app = create_app()
    def override():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app, base_url="https://testserver") as client:
        yield client, engine
    engine.dispose()

def login(client, password=PASSWORD):
    return client.post("/api/auth/login", json={"username":"admin","password":password}, headers=ORIGIN)

def test_login_logout(setup):
    client, engine = setup
    assert client.get("/api/auth/me").status_code == 401
    response = login(client)
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    with Session(engine) as db:
        session = db.scalar(select(LoginSession))
        assert session.token_hash != client.cookies.get("jiaoyan_session")
    assert client.get("/api/auth/me").json() == {"username":"admin"}
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 200
    assert client.get("/api/auth/me").status_code == 401

def test_origin_and_lockout(setup):
    client, _ = setup
    assert client.post("/api/auth/login", json={"username":"admin","password":PASSWORD}).status_code == 403
    for _ in range(5):
        assert login(client, "wrong").status_code == 401
    assert login(client).status_code == 429

def test_password_change_revokes_old_session(setup):
    client, _ = setup
    assert login(client).status_code == 200
    old = client.cookies.get("jiaoyan_session")
    new_password = "replacement-password-123"
    response = client.post("/api/auth/password", headers=ORIGIN,
                           json={"current_password":PASSWORD,"new_password":new_password})
    assert response.status_code == 200
    assert client.cookies.get("jiaoyan_session") != old
    with TestClient(client.app, base_url="https://testserver", cookies={"jiaoyan_session":old}) as other:
        assert other.get("/api/auth/me").status_code == 401
    assert login(client, new_password).status_code == 200
