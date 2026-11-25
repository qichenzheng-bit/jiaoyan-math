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
        setup=client.post("/api/documents/setup",headers=origin,json={"title":"UI录入测试","source_type":"exam","subject":"高等数学","exam_type":"数学一","year":"2026","intro":"卷头说明"})
        assert setup.status_code==200,setup.text
        created_doc=setup.json()
        assert created_doc["blocks"][0]["content"]=="卷头说明"
        assert client.get("/api/resources/"+created_doc["source_id"]).json()["source_type"]=="exam"
        assert client.post("/api/documents/setup",headers=origin,json={"title":"UI录入测试","source_type":"exam","subject":"高等数学","exam_type":"数学一","year":"2026","intro":"卷头说明"}).status_code==409
        assert client.post("/api/documents/setup",headers=origin,json={"title":"UI录入测试","source_type":"exam","subject":"高等数学","exam_type":"数学一","year":"2026","intro":"不同备注"}).status_code==409
        match=client.post("/api/resources/source-matches",headers=origin,json={"kind":"source","title":"UI录入测试","source_type":"exam","cohort_year":"2026","content":"其他说明"})
        assert match.status_code==200 and match.json()[0]["id"]==created_doc["source_id"]
        reused=client.post("/api/documents/setup",headers=origin,json={"title":"第二批","subject":"高等数学","existing_source_id":created_doc["source_id"]})
        assert reused.status_code==200,reused.text
        assert reused.json()["source_id"]==created_doc["source_id"]
        assert client.get("/api/documents?kind=intake&source_id="+created_doc["source_id"]).json()["total"]==2
        assert client.post("/api/resources",headers=origin,json={"kind":"source","title":"UI录入测试","source_type":"exam","cohort_year":"2026","content":"不同文本"}).status_code==409
        assert client.post("/api/resources",headers=origin,json={"kind":"source","title":"UI录入测试","source_type":"exam","cohort_year":"2027","content":"卷头说明"}).status_code==200
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
        kp=client.post("/api/knowledge/points",headers=origin,json={"name":"极限","subject":"高等数学","aliases":["limit"]})
        assert kp.status_code==200,kp.text
        k=kp.json()
        other=client.post("/api/knowledge/points",headers=origin,json={"name":"函数极限","subject":"高等数学"}).json()
        edge={"source_id":k["id"],"target_id":other["id"],"relation_type":"contains"}
        assert client.post("/api/knowledge/relations",headers=origin,json=edge).status_code==200
        assert client.post("/api/knowledge/relations",headers=origin,json={**edge,"source_id":other["id"],"target_id":k["id"]}).status_code==409
        assert client.get("/api/knowledge/points?q=limit").json()["total"]==1
        link=client.get("/api/knowledge/resources/"+rid).json()
        assert client.put("/api/knowledge/resources/"+rid,headers=origin,json={"revision":link["revision"],"items":[{"knowledge_id":k["id"],"role":"core"}]}).status_code==200
        assert client.get("/api/knowledge/points/"+k["id"]+"/resources").json()[0]["id"]==rid
        doc=client.post("/api/documents",headers=origin,json={"title":"录入测试","subject":"高数","blocks":[{"uid":"a","kind":"question","title":"新题","content":"求导数","answer":"1"}]})
        assert doc.status_code==200,doc.text
        d=doc.json()
        registered=client.post("/api/documents/"+d["id"]+"/blocks/a/register",headers=origin,json={"revision":d["revision"]})
        assert registered.status_code==200,registered.text
        rd=registered.json()
        assert rd["blocks"][0]["snapshot"]["code"].startswith("Q")
        assert rd["blocks"][0]["kind"]=="reference"
        assert client.put("/api/documents/"+d["id"],headers=origin,json=d).status_code==409
        updated=client.put("/api/documents/"+d["id"],headers=origin,json={**rd,"title":"修订标题"})
        assert updated.status_code==200,updated.text
        assert updated.json()["blocks"][0]["snapshot"]==rd["blocks"][0]["snapshot"]
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
        paper=client.post("/api/documents",headers=origin,json={"title":"试卷测试","kind":"paper","blocks":[{"uid":"q","kind":"reference","resource_id":rid,"score":10}]} )
        assert paper.status_code==200,paper.text
        paper=paper.json()
        assert paper["blocks"][0]["score"]==10
        promoted=client.post("/api/documents/"+paper["id"]+"/promote",headers=origin,json={"revision":paper["revision"]})
        assert promoted.status_code==200,promoted.text
        assert promoted.json()["source_id"]
        assert client.get("/api/resources/"+rid).json()["source_id"]==source["id"]
        assert client.get("/api/chat/resource-search?q="+created.json()["code"]).json()[0]["id"]==rid
        assert client.get("/api/tasks").status_code==200
        assert client.post("/api/tasks/sync",headers=origin).status_code==200
        assert client.post("/api/intelligence/pdf-text",headers=origin,json={"file_id":item["id"]}).status_code==415
        from app.api import intelligence
        # Source identity is resolved from saved messages, never from caller-supplied role.
        saved_chat=client.get("/api/chat/sessions/"+chat_id).json()
        user_message=next(m for m in saved_chat["messages"] if m["role"]=="user")
        source_message=client.get("/api/intelligence/chat-source/"+user_message["id"])
        assert source_message.status_code==200 and source_message.json()["role"]=="user"
        assert client.get("/api/intelligence/chat-source/missing").status_code==404
        def fake_ingest(method,path,body=None):
            if path=="/status":return {"chat_available":True}
            if path=="/chat/start":return {"state":"running"}
            return {"state":"done","answer":'[{"kind":"question","title":"测试提取","content":"求极限"}]'}
        monkeypatch.setattr(qoder,"request",fake_ingest)
        job=client.post("/api/intelligence/jobs",headers=origin,json={"title":"提取测试","text":"求极限","subject":"高数","source_message_id":user_message["id"],"intent":"question","source_id":created_doc["source_id"]})
        assert job.status_code==200,job.text
        j=client.get("/api/intelligence/jobs/"+job.json()["id"]).json()
        assert j["provenance"]["kind"]=="chat_user"
        assert j["provenance"]["message_id"]==user_message["id"]
        assert j["provenance"]["edited"] is True
        assert j["provenance"]["intent"]=="question"
        assert client.post("/api/intelligence/jobs/"+j["id"]+"/retry",headers=origin,json={"revision":j["revision"]}).status_code==409
        assert j["state"]=="review" and j["source_id"]==created_doc["source_id"]
        converted=client.post("/api/intelligence/jobs/"+j["id"]+"/document",headers=origin,json={"revision":j["revision"]})
        assert converted.status_code==200,converted.text
        converted_doc=client.get("/api/documents/"+converted.json()["document_id"]).json()
        assert converted_doc["blocks"][0]["kind"]=="question"
        assert converted_doc["source_id"]==created_doc["source_id"]
        def failed_ingest(method,path,body=None):
            if path=="/status":return {"chat_available":True}
            if path=="/chat/start":return {"state":"running"}
            return {"state":"failed","detail":"测试失败"}
        monkeypatch.setattr(qoder,"request",failed_ingest)
        failed=client.post("/api/intelligence/jobs",headers=origin,json={"title":"重试测试","text":"求导","source_message_id":user_message["id"]}).json()
        failed=client.get("/api/intelligence/jobs/"+failed["id"]).json()
        assert failed["state"]=="failed"
        monkeypatch.setattr(qoder,"request",fake_ingest)
        retry_url="/api/intelligence/jobs/"+failed["id"]+"/retry"
        retry_body={"revision":failed["revision"]}
        retried=client.post(retry_url,headers=origin,json=retry_body)
        assert retried.status_code==200,retried.text
        assert retried.json()["retry_of"]==failed["id"]
        assert retried.json()["provenance"]==failed["provenance"]
        assert client.post(retry_url,headers=origin,json=retry_body).json()["id"]==retried.json()["id"]
        asset=client.post("/api/studio",headers=origin,json={"kind":"asset","title":"常用公式","data":{"category":"formula","content":"x^2"}})
        assert asset.status_code==200,asset.text
        a=asset.json()
        assert client.put("/api/studio/"+a["id"],headers=origin,json={"kind":"asset","title":"修改公式","data":a["data"],"revision":a["revision"]}).status_code==200
        assert len(client.get("/api/studio/"+a["id"]+"/versions").json())==2
        assert client.get("/api/studio?kind=asset&category=formula").json()["total"]==1
        assert client.get("/api/studio?kind=asset&category=image").json()["total"]==0
        assert client.get("/api/studio?kind=asset&favorite=true").json()["total"]==0
        work=client.post("/api/studio",headers=origin,json={"kind":"work","title":"作品","data":{"category":"article","content":"正文"}}).json()
        assert client.post("/api/studio",headers=origin,json={"kind":"publication","title":"发布","data":{"platform":"xiaohongshu","work_id":work["id"],"state":"published"}}).status_code==422
        account=client.post("/api/studio",headers=origin,json={"kind":"account","title":"测试账户","data":{"platform":"qoder_cn"}}).json()
        check={"kind":"checkin","title":"签到","data":{"account_id":account["id"],"day":"2026-11-25","state":"success","earned":2}}
        assert client.post("/api/studio",headers=origin,json=check).status_code==200
        assert client.post("/api/studio",headers=origin,json=check).status_code==409
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
