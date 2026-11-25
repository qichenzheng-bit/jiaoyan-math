from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.db import Base,get_db
from app.core.config import settings
from app.core.security import hash_password,now
from app.main import create_app
from app.models import User

def test_preferences():
    engine=create_engine("sqlite://",poolclass=StaticPool,connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1,username="admin",password_hash=hash_password("test-password-123"),created_at=now()))
        db.commit()
    app=create_app()
    def override():
        with Session(engine,expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[get_db]=override
    with TestClient(app,base_url="https://testserver") as client:
        assert client.get("/api/settings").status_code==401
        origin={"Origin":settings.app_origin}
        assert client.post("/api/auth/login",headers=origin,json={"username":"admin","password":"test-password-123"}).status_code==200
        value={"display_name":"教研测试","theme":"dark"}
        assert client.put("/api/settings",json=value).status_code==403
        assert client.put("/api/settings",headers=origin,json=value).status_code==200
        assert client.get("/api/settings").json()==value
        assert client.put("/api/settings",headers=origin,json={**value,"theme":"invalid"}).status_code==422
        assert client.get("/api/settings/audit").status_code==200
    engine.dispose()
