import json
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
    monkeypatch.setenv("WG_RECOMMENDATION_SCHEDULER","0")
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
        catalog_url="/api/source-catalog/sources/"+created_doc["source_id"]
        old_catalog=client.get(catalog_url).json()
        assert old_catalog["revision"]==0 and old_catalog["intake_status"]=="unknown"
        metadata={"revision":0,"category":"院校真题","institution":"测试院校","subject_code":"601","subjects":["高数","线性代数"],"intake_status":"in_progress"}
        saved=client.put(catalog_url,headers=origin,json=metadata)
        assert saved.status_code==200,saved.text
        assert saved.json()["subjects"]==["高等数学","线性代数"]
        assert client.put(catalog_url,headers=origin,json=metadata).status_code==409
        found=client.get("/api/source-catalog/sources",params={"institutions":"测试院校","years":"2026"}).json()
        assert found["total"]==1 and found["items"][0]["source_id"]==created_doc["source_id"]
        assert len(client.get(catalog_url+"/history").json()["items"])==1
        actual=client.get("/api/resources/"+created_doc["source_id"]+"/source-overview").json()
        assert actual["questions"]==actual["knowledge"]==actual["knowledge_tags"]==0
        assert "total_questions" not in actual
        assert created_doc["blocks"][0]["content"]=="卷头说明"
        assert created_doc["subject"]==""
        assert client.get("/api/resources/"+created_doc["source_id"]).json()["subject"]==""
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
        work=client.post("/api/workspaces",headers=origin,json={"title":"持续录入测试"}).json()
        linked=client.post("/api/workspaces/"+work["id"]+"/materials",headers=origin,json={"file_ids":[item["id"]]}).json()
        mid=linked["materials"][0]["id"]
        assert client.post("/api/files/"+item["id"]+"/archive",headers=origin).status_code==409
        base="/api/workspaces/"+work["id"]
        batch=client.post(base+"/materials/"+mid+"/batches",headers=origin,json={"start":1,"end":1}).json()
        bid=batch["id"]
        assert client.post(base+"/batches/"+bid+"/verify",headers=origin,json={"text":"test file"}).status_code==409
        assert client.post(base+"/batches/"+bid+"/step",headers=origin).json()["units"][0]["text"]=="test file"
        assert client.post(base+"/batches/"+bid+"/verify",headers=origin,json={"text":"test file"}).json()["verified"]
        assert client.get(base).json()["materials"][0]["verified_units"]==1
        second=client.post("/api/workspaces",headers=origin,json={"title":"跨会话继续"}).json()
        second_base="/api/workspaces/"+second["id"]
        second_material=client.post(second_base+"/materials",headers=origin,json={"file_ids":[item["id"]]}).json()["materials"][0]
        assert second_material["recognized_units"]==1 and second_material["verified_units"]==1 and second_material["next_unit"]==2
        assert client.get(second_base+"/batches/"+bid).json()["verified"]
        assert client.get("/api/workspaces/library?q=notes.txt").json()["items"][0]["verified_units"]==1
        assert client.get("/api/workspaces/library/resolve?instruction=notes.txt%20继续识别").json()["items"][0]["id"]==item["id"]
        assert client.post("/api/workspaces/library/archive",headers=origin,json={"file_ids":[item["id"]]}).status_code==409
        assert client.post("/api/workspaces/library/archive",headers=origin,json={"file_ids":[item["id"]],"allow_unfinished":True}).status_code==200
        assert client.get(base).json()["materials"][0]["file"]["archived"]
        assert client.get("/api/workspaces/library?archived=true").json()["total"]>=1
        assert client.post("/api/workspaces/library/"+item["id"]+"/restore",headers=origin).status_code==200
        assert client.post(base+"/materials/"+mid+"/batches",headers=origin,json={"start":1,"end":1}).json()["id"]==bid
        draft={"kind":"question","title":"极限","subject":"高数","content":"求极限","solution":"方法"}
        created=client.post("/api/resources",headers=origin,json=draft)
        assert created.status_code==200,created.text
        assert created.json()["question_data"]["version"]==1 and created.json()["question_data"]["stem"]==draft["content"]
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
        root_browse=client.get("/api/knowledge/browse",params={"subject":"高等数学"}).json()
        assert root_browse["mode"]=="chapters"
        assert any(x["chapter"]=="" for x in root_browse["items"])
        roots=client.get("/api/knowledge/browse",params={"subject":"高等数学","chapter":""}).json()
        assert roots["mode"]=="points"
        assert any(x["id"]==k["id"] and x["child_count"]==1 for x in roots["items"])
        assert all(x["id"]!=other["id"] for x in roots["items"])
        children=client.get("/api/knowledge/browse",params={"subject":"高等数学","parent_id":k["id"]}).json()
        assert [x["id"] for x in children["items"]]==[other["id"]]
        search=client.get("/api/knowledge/browse",params={"subject":"高等数学","q":"limit"}).json()
        assert [x["id"] for x in search["items"]]==[k["id"]]
        assert client.get("/api/knowledge/browse",params={"subject":"线性代数","parent_id":k["id"]}).status_code==422

        link=client.get("/api/knowledge/resources/"+rid).json()
        assert client.put("/api/knowledge/resources/"+rid,headers=origin,json={"revision":link["revision"],"items":[{"knowledge_id":k["id"],"role":"core"}]}).status_code==200
        assert client.get("/api/knowledge/points/"+k["id"]+"/resources").json()[0]["id"]==rid
        doc=client.post("/api/documents",headers=origin,json={"title":"录入测试","subject":"高数","source_id":created_doc["source_id"],"blocks":[{"uid":"a","kind":"question","title":"新题","content":"求导数","answer":"1","question_type":"综合题"}]})
        assert doc.status_code==200,doc.text
        d=doc.json()
        assert client.post("/api/documents/"+d["id"]+"/blocks/a/register",headers=origin,json={"revision":d["revision"]}).status_code==409
        def approve_and_commit(path,doc):
            checked=client.post(path+"/manual-review",headers=origin,json={"revision":doc["revision"]})
            assert checked.status_code==200,checked.text
            for item in checked.json()["rows"]:
                approval=client.post(path+"/manual-review-progress",headers=origin,json={"revision":doc["revision"],"uid":item["uid"],"approved":True})
                assert approval.status_code==200,(approval.text,item,checked.text)
            return client.post(path+"/manual-commit",headers=origin,json={"revision":doc["revision"],"accept_warnings":True})
        registered=approve_and_commit("/api/documents/"+d["id"],d)
        assert registered.status_code==200,registered.text
        rd=registered.json()["document"]
        assert rd["blocks"][0]["snapshot"]["code"].startswith("Q")
        assert rd["blocks"][0]["kind"]=="reference"
        assert client.put("/api/documents/"+d["id"],headers=origin,json=d).status_code==409
        updated=client.put("/api/documents/"+d["id"],headers=origin,json={**rd,"title":"修订标题"})
        assert updated.status_code==200,updated.text
        assert updated.json()["blocks"][0]["snapshot"]==rd["blocks"][0]["snapshot"]
        # Full-library stem matching and transactional registration.
        batch=client.post("/api/documents",headers=origin,json={"title":"批量审核","subject":"高数","source_id":created_doc["source_id"],"blocks":[
            {"uid":"same","kind":"question","title":"极限","content":"求极限","solution":"另一种解法","question_type":"综合题"},
            {"uid":"new","kind":"question","title":"新问题","content":"计算新的定积分","answer":"2","question_type":"综合题","dedup_reason":"测试独立题目"}]}).json()
        base="/api/documents/"+batch["id"]
        review=client.post(base+"/registration-preview",headers=origin,json={"revision":batch["revision"],"block_ids":["same","new"]})
        assert review.status_code==200,review.text
        match=next(x for x in review.json()["items"][0]["candidates"] if x["id"]==rid)
        assert match["kind"]=="same_stem" and match["appendable"]
        manual_matches=client.post("/api/resources/similar",headers=origin,json={"kind":"question","title":"极限","content":"求极限","solution":"另一种解法"}).json()
        assert any(c["resource"]["id"]==rid and c["match_kind"]=="same_stem" for c in manual_matches["items"])
        assert any(p["id"]==k["id"] for p in review.json()["items"][0]["knowledge"])
        choices=[{"uid":"new","action":"create","reason":"测试独立题目"},{"uid":"same","action":"append","resource_id":rid,"resource_revision":match["revision"],"knowledge_ids":["missing"]}]
        count=client.get("/api/resources?kind=question").json()["total"]
        failure=client.post(base+"/registration-commit",headers=origin,json={"revision":batch["revision"],"preview_token":review.json()["preview_token"],"items":choices,"accept_warnings":True})
        assert failure.status_code==422,failure.text
        assert client.get("/api/resources?kind=question").json()["total"]==count
        assert client.get(base).json()["revision"]==batch["revision"]
        choices[1]["knowledge_ids"]=[k["id"]]
        committed=client.post(base+"/registration-commit",headers=origin,json={"revision":batch["revision"],"preview_token":review.json()["preview_token"],"items":choices,"accept_warnings":True})
        assert committed.status_code==200,committed.text
        assert all(x["kind"]=="reference" for x in committed.json()["blocks"])
        assert "另一种解法" in client.get("/api/resources/"+rid).json()["solution"]
        assert "方法" in client.get("/api/resources/"+rid).json()["solution"]
        history=client.get(base+"/registration-history").json()
        assert history[0]["count"]==2
        record=client.get(base+"/registration-history/"+history[0]["id"]).json()
        assert next(e for e in record["entries"] if e["uid"]=="same")["input"]["solution"]=="另一种解法"
        assert client.post(base+"/registration-commit",headers=origin,json={"revision":batch["revision"],"preview_token":review.json()["preview_token"],"items":choices,"accept_warnings":True}).status_code==409
        # Phone entry saves the draft, confirms each item, then registers it atomically.
        manual=reused.json()
        manual_path="/api/documents/"+manual["id"]
        draft_blocks=[
            {"uid":"manual-heading","kind":"heading","title":"一、选择题"},
            {"uid":"manual-a","kind":"question","subject":"线性代数","question_type":"选择题","difficulty":"中等","chapter":"矩阵","knowledge_tags":["矩阵运算","矩阵运算"],"content":"选择正确项\nA. 1\nB. 2","answer":"AB","solution":"已知解析"},
            {"uid":"manual-b","kind":"question","subject":"高等数学","question_type":"解答题","content":"已知函数\n(1) 求导数","dedup_reason":"独立测试小问题","answer":"(1) 2x","solution":"(1) 直接计算"},
        ]
        before_count=client.get("/api/resources?kind=question").json()["total"]
        bad=client.post(manual_path+"/manual-save",headers=origin,json={**manual,"blocks":[*draft_blocks,{"uid":"bad","kind":"question","content":""}]})
        assert bad.status_code==409
        assert client.get("/api/resources?kind=question").json()["total"]==before_count
        assert client.get(manual_path).json()["revision"]==manual["revision"]
        no_subject=client.post(manual_path+"/manual-save",headers=origin,json={**manual,"blocks":[draft_blocks[0],{**draft_blocks[1],"subject":""}]})
        assert no_subject.status_code==409
        drafted=client.put(manual_path+"/manual-draft",headers=origin,json={**manual,"blocks":draft_blocks})
        assert drafted.status_code==200,drafted.text
        saved=approve_and_commit(manual_path,drafted.json())
        assert saved.status_code==200,saved.text
        from types import SimpleNamespace
        saved=SimpleNamespace(json=lambda:client.get(manual_path).json())
        assert saved.json()["blocks"][1]["snapshot"]["subject"]=="线性代数"
        assert saved.json()["blocks"][1]["snapshot"]["chapter"]=="矩阵"
        assert saved.json()["blocks"][1]["snapshot"]["answer"]=="AB"
        assert saved.json()["blocks"][1]["snapshot"]["question_type"]=="多选题"
        assert saved.json()["blocks"][1]["snapshot"]["difficulty"]=="中等"
        assert saved.json()["blocks"][2]["snapshot"]["content"].endswith("(1) 求导数")
        assert saved.json()["blocks"][2]["snapshot"]["question_type"]=="综合题"
        assert saved.json()["blocks"][2]["snapshot"]["subject"]=="高等数学"
        assert saved.json()["blocks"][1]["snapshot"]["source_id"]==saved.json()["blocks"][2]["snapshot"]["source_id"]==manual["source_id"]
        assert any(x["id"]==saved.json()["blocks"][2]["snapshot"]["id"] for x in client.get("/api/resources",params={"kind":"question","question_type":"综合题"}).json()["items"])
        assert client.post(manual_path+"/manual-save",headers=origin,json={**manual,"blocks":draft_blocks}).status_code==409
        assert client.get(manual_path+"/export").status_code==409
        exported=client.get("/api/documents/source-export/"+manual["source_id"])
        assert exported.status_code==200,exported.text
        assert any(b.get("snapshot",{}).get("content","").startswith("选择正确项") for b in exported.json()["blocks"])
        original=saved.json()["blocks"][1]["snapshot"]
        assert original["tags"]==["矩阵运算"]
        linked=client.get("/api/knowledge/resources/"+original["id"]).json()["items"]
        assert len(linked)==1 and linked[0]["name"]=="矩阵运算"
        found=client.post("/api/documents/manual-matches",headers=origin,json={k:original[k] for k in ("content","answer","solution")})
        assert found.status_code==200,found.text
        assert found.json()["scope"]=="full_active_question_bank"
        assert any(x["resource"]["id"]==original["id"] and x["match_kind"]=="exact" for x in found.json()["items"])
        assert found.json()["threshold"]==0.8
        # More than ten equal stems must all survive duplicate search.
        match_ids=set()
        stem="求函数在给定区间上的极限值并写出详细计算步骤"
        from app.models import TeachingResource
        from app.core.content_normalization import question_fingerprint,question_stem_key
        from uuid import uuid4
        variant=client.post("/api/resources",headers=origin,json={"kind":"question","title":"查重测试","subject":"高等数学","content":stem,"answer":"0","solution":"逐步计算"})
        assert variant.status_code==200,variant.text
        match_ids.add(variant.json()["id"])
        assert client.post("/api/resources",headers=origin,json={"kind":"question","title":"查重测试","subject":"高等数学","content":stem,"answer":"1","solution":"另一种解法","dedup_override":True,"dedup_reason":"测试"}).status_code==409
        # Simulate historical duplicates created before question-first uniqueness.
        with session_factory()() as db:
            for j in range(1,12):
                ident=str(uuid4());match_ids.add(ident)
                db.add(TeachingResource(id=ident,code="Q"+uuid4().hex[:8].upper(),kind="question",title="旧查重测试",subject="高等数学",content=stem,answer=str(j),solution="逐步计算",tags=[],fingerprint=question_fingerprint(stem,"逐步计算",str(j)),stem_key=question_stem_key(stem),archived=False,created_at=1,updated_at=1))
            db.commit()
        matched=client.post("/api/documents/manual-matches",headers=origin,json={"content":stem,"answer":"0","solution":"逐步计算"})
        assert matched.status_code==200,matched.text
        assert match_ids <= {x["resource"]["id"] for x in matched.json()["items"]}
        assert all(x["similarity"]>=0.8 for x in matched.json()["items"])
        assert matched.json()["total"]==len(matched.json()["items"])
        assert "ix_resource_search_features" in {x["name"] for x in inspect(engine()).get_indexes("teaching_resources")}
        # Exercise the actual indexed branch above its activation threshold, not only the small-library fallback.
        from app.core.search_features import search_features
        from sqlalchemy import delete
        filler_ids=[]
        with session_factory()() as db:
            rows=[]
            for i in range(1000):
                ident=str(uuid4());filler_ids.append(ident)
                text="几何图形陌生检索样本"+str(i)
                rows.append(dict(id=ident,code="Q"+uuid4().hex[:12].upper(),kind="question",title="索引样本",subject="高等数学",content=text,answer="",solution="",tags=[],fingerprint=question_fingerprint(text,"",""),stem_key=question_stem_key(text),search_features=search_features(text),archived=False,created_at=now(),updated_at=now()))
            db.bulk_insert_mappings(TeachingResource,rows);db.commit()
        indexed=client.post("/api/documents/manual-matches",headers=origin,json={"content":stem,"answer":"0","solution":"逐步计算"})
        assert indexed.status_code==200,indexed.text
        assert match_ids<={x["resource"]["id"] for x in indexed.json()["items"]}
        assert indexed.json()["scanned"]<1000
        with session_factory()() as db:
            db.execute(delete(TeachingResource).where(TeachingResource.id.in_(filler_ids)));db.commit()

        new_source=client.post("/api/documents/setup",headers=origin,json={"title":"复用试卷","subject":"线性代数","source_type":"exam"}).json()
        reuse_path="/api/documents/"+new_source["id"]+"/manual-save"
        reused_block={**draft_blocks[1],"question_type":original["question_type"],"uid":"reuse-question","reuse_resource_id":original["id"],"reuse_revision":original["revision"],"knowledge_tags":["矩阵运算","矩阵乘法"]}
        changed=client.post(reuse_path,headers=origin,json={**new_source,"blocks":[{**reused_block,"content":"篡改原题"}]})
        assert changed.status_code==409
        assert client.get("/api/documents/"+new_source["id"]).json()["revision"]==new_source["revision"]
        reuse_base=reuse_path.removesuffix("/manual-save")
        reuse_draft=client.put(reuse_base+"/manual-draft",headers=origin,json={**new_source,"blocks":[reused_block]})
        assert reuse_draft.status_code==200,reuse_draft.text
        reused_saved=approve_and_commit(reuse_base,reuse_draft.json())
        assert reused_saved.status_code==200,reused_saved.text
        reused_saved=SimpleNamespace(json=lambda:client.get(reuse_base).json())
        same=reused_saved.json()["blocks"][0]["snapshot"]
        assert same["id"]==original["id"] and same["code"]==original["code"]
        assert same["content"]==original["content"]
        src_links=client.get("/api/resources/"+original["id"]+"/sources").json()["items"]
        assert any(l["source_id"]==new_source["source_id"] and l["occurrences"] for l in src_links)
        assert {"矩阵运算","矩阵乘法"}==set(same["tags"])
        assert new_source["source_id"] in {x["source_id"] for x in client.get("/api/resources/"+same["id"]+"/sources").json()["items"]}
        fork={**reused_block,"uid":"fork-question","content":"另一个矩阵选择题\nA. 1\nB. 2","reuse_resource_id":None,"reuse_revision":None,"fork_from_id":same["id"]}
        reused_doc=reused_saved.json()
        fork_draft=client.put(reuse_base+"/manual-draft",headers=origin,json={**reused_doc,"blocks":[*reused_doc["blocks"],{**fork,"dedup_reason":"独立矩阵测试"}]})
        assert fork_draft.status_code==200,fork_draft.text
        fork_saved=approve_and_commit(reuse_base,fork_draft.json())
        assert fork_saved.status_code==200,fork_saved.text
        fork_saved=SimpleNamespace(json=lambda:client.get(reuse_base).json())
        new=fork_saved.json()["blocks"][1]["snapshot"]
        assert new["code"]!=same["code"] and new["id"]!=same["id"]
        assert client.get("/api/resources/"+same["id"]).json()["content"]==same["content"]
        # Same-batch review merges only after explicit confirmation and records both source occurrences.
        duplicate_batch=client.post("/api/documents/setup",headers=origin,json={"title":"同批同题专项","source_type":"exam"}).json()
        duplicate_path="/api/documents/"+duplicate_batch["id"]
        q="求特殊参数曲线的独立测试极限 $\\lim_{x\\to0} x$"
        block={"kind":"question","content":q,"subject":"高等数学","question_type":"综合题","answer":"0","solution":"直接代入法","uid":"same-one","original_question_number":"1","source_page_start":2}
        batch_draft=client.put(duplicate_path+"/manual-draft",headers=origin,json={**duplicate_batch,"blocks":[block,{**block,"uid":"same-two","solution":"连续性法","original_question_number":"7","source_page_start":5}]})
        assert batch_draft.status_code==200,batch_draft.text
        version=batch_draft.json()["revision"]
        checks=client.post(duplicate_path+"/manual-review",headers=origin,json={"revision":version}).json()
        assert [r["action"] for r in checks["rows"]]==["create","batch_reuse"],checks
        for uid in ("same-one","same-two"):
            checked=client.post(duplicate_path+"/manual-review-progress",headers=origin,json={"revision":version,"uid":uid,"approved":True})
            assert checked.status_code==200,checked.text
        merged=client.post(duplicate_path+"/manual-commit",headers=origin,json={"revision":version,"accept_warnings":True,"require_reviewed":True})
        assert merged.status_code==200,merged.text
        same_blocks=merged.json()["document"]["blocks"]
        merged_id=same_blocks[0]["resource_id"]
        assert same_blocks[1]["resource_id"]==merged_id
        merged_resource=client.get("/api/resources/"+merged_id).json()
        bank_page=client.get("/api/resources",params={"kind":"question","q":merged_resource["code"],"bank_summary":True}).json()
        summary=next(r["bank_summary"] for r in bank_page["items"] if r["id"]==merged_id)
        assert summary["source_count"]==1 and summary["method_count"]==2 and summary["has_answer"] and summary["has_solution"]
        assert summary["source_title"]
        def bank_search(**kw):
            response=client.get("/api/resources",params={"kind":"question","bank_summary":True,"q":merged_resource["code"],**kw})
            assert response.status_code==200,response.text
            return response.json()["total"]
        assert bank_search(method_state="multi",integrity="complete")==1
        assert bank_search(method_state="single")==0
        assert bank_search(original_number="7",original_page=5)==1
        assert bank_search(original_number="7",original_page=2)==0
        assert bank_search(source_count="single",sort="sources")==1
        assert bank_search(source_count="multiple")==0
        assert bank_search(sort="number")==1
        assert bank_search(sort="year")==1
        assert bank_search(method_state="pending")==1
        assert "直接代入法" in merged_resource["solution"] and "连续性法" in merged_resource["solution"]
        occurrences=client.get("/api/resources/"+merged_id+"/sources").json()["items"][0]["occurrences"]
        assert {(o["original_question_number"],o["page_start"]) for o in occurrences}=={("1",2),("7",5)}
        from app.api import qoder
        monkeypatch.setattr(qoder,"available_models",lambda:{"source":"cli","models":[{"id":"Auto","efforts":["high","medium"]},{"id":"Qwen4-Max","efforts":["low"]}]})
        assert client.get("/api/qoder/preferences").json()=={"model":"Auto","video_model":"Auto","effort":"default","video_effort":"default"}
        assert client.put("/api/qoder/preferences",headers=origin,json={"model":"Qwen4-Max"}).status_code==200
        assert client.get("/api/qoder/preferences").json()=={"model":"Qwen4-Max","video_model":"Auto","effort":"default","video_effort":"default"}
        assert client.put("/api/qoder/preferences",headers=origin,json={"model":"Qwen4-Max","video_model":"Qwen4-Max"}).status_code==200
        assert client.get("/api/qoder/preferences").json()=={"model":"Qwen4-Max","video_model":"Qwen4-Max","effort":"default","video_effort":"default"}
        assert client.put("/api/qoder/preferences",headers=origin,json={"model":"Qwen4-Max","video_model":"Unknown"}).status_code==422
        assert client.put("/api/qoder/preferences",headers=origin,json={"model":"Unknown"}).status_code==422
        assert client.put("/api/qoder/preferences",json={"model":"Auto"}).status_code==403
        # Fake model response exercises the durable AI recommendation lifecycle, not real teaching quality.
        def fake_recommendation(method,path,body=None):
            if path=="/chat/start":return {"state":"running"}
            return {"state":"done","answer":json.dumps({"choices":{"main":2},"reason":"连续性法更便于课堂讲解"},ensure_ascii=False)}
        monkeypatch.setattr(qoder,"request",fake_recommendation)
        rec_path="/api/resources/"+merged_id+"/recommendation"
        rec=client.get(rec_path).json()
        assert len(rec["groups"][0]["methods"])==2
        assert rec["evaluation"]["state"]=="queued"
        rec_revision=rec["revision"]
        from app.services.recommendation_worker import process_one
        process_one(merged_id,1)
        assert client.get(rec_path).json()["evaluation"]["state"]=="running"
        process_one(merged_id,1)
        suggested=client.post(rec_path+"/poll",headers=origin,json={"revision":rec_revision}).json()
        assert suggested["state"]=="review",suggested
        confirmed=client.post(rec_path+"/confirm",headers=origin,json={"revision":rec_revision,"choices":suggested["choices"]})
        assert confirmed.status_code==200,confirmed.text
        assert confirmed.json()["evaluation"]["reason"]=="连续性法更便于课堂讲解"
        assert bank_search(method_state="confirmed")==1
        # Independent method edit and version conflict; existing recommendation is preserved until human confirmation.
        m=client.post("/api/bank/questions/"+merged_id+"/methods",headers=origin,json={"revision":confirmed.json()["revision"],"group":"main","action":"add","name":"代数法","body":"第三种独立解法"})
        assert m.status_code==200,m.text
        assert len(m.json()["groups"][0]["methods"])==3
        assert client.post("/api/bank/questions/"+merged_id+"/methods",headers=origin,json={"revision":confirmed.json()["revision"],"group":"main","action":"delete","index":1}).status_code==409
        assert client.get("/api/bank/questions/"+merged_id+"/history").json()
        assert client.get("/api/bank/questions/"+merged_id+"/video-preview").json()["ready"]
        deleted=client.post("/api/bank/questions/"+merged_id+"/methods",headers=origin,json={"revision":m.json()["revision"],"group":"main","action":"delete","index":3})
        assert deleted.status_code==200,deleted.text
        assert len(deleted.json()["groups"][0]["methods"])==2
        reconfirmed=client.post(rec_path+"/confirm",headers=origin,json={"revision":deleted.json()["revision"],"choices":{"main":2}})
        assert reconfirmed.status_code==200,reconfirmed.text
        assert bank_search(method_state="pending")==0
        # Source filters may not combine the year from one source and exam from another.
        source_a=client.post("/api/resources",headers=origin,json={"kind":"source","title":"组合筛选真题A","content":"测试","source_type":"exam","cohort_year":"2018","exam_type":"数学一","authority_tier":"official_exam"}).json()
        source_b=client.post("/api/resources",headers=origin,json={"kind":"source","title":"组合筛选真题B","content":"测试","source_type":"exam","cohort_year":"2025","exam_type":"数学二","authority_tier":"official_exam"}).json()
        seed=client.post("/api/resources",headers=origin,json={"kind":"question","title":"组合筛选独立题","content":"某可微函数于指定点的导数存在性","answer":"存在","solution":"泰勒公式","subject":"高等数学","question_type":"综合题","source_id":source_a["id"],"tags":["专项甲","专项乙"]}).json()
        relation=client.get("/api/resources/"+seed["id"]+"/sources").json()
        linked=client.put("/api/resources/"+seed["id"]+"/sources",headers=origin,json={"revision":relation["revision"],"items":[{"source_id":source_a["id"],"is_primary":True,"original_question_number":"10"},{"source_id":source_b["id"],"is_primary":False,"original_question_number":"2"}]})
        assert linked.status_code==200,linked.text
        stats_path="/api/source-catalog/statistics"
        assert client.post(stats_path,headers=origin,json={}).status_code==422
        aggregate=client.post(stats_path,headers=origin,json={"source_ids":[source_a["id"],source_b["id"],source_a["id"]]})
        assert aggregate.status_code==200,aggregate.text
        data=aggregate.json()
        assert data["source_count"]==2 and data["question_count"]==1 and data["source_question_count"]==2
        assert data["knowledge_count"]==2 and data["questions_with_knowledge"]==1
        assert data["original_question_total"] is None and data["confirmed_complete_sources"]==0
        assert {r["name"] for r in data["items"]}=={"专项甲","专项乙"}
        assert all(r["question_count"]==1 and r["source_question_count"]==2 for r in data["items"])
        single=client.post(stats_path,headers=origin,json={"source_ids":[source_a["id"],source_b["id"]],"years":["2018"]}).json()
        assert single["source_count"]==1 and single["source_question_count"]==1
        assert len(client.post(stats_path,headers=origin,json={"source_ids":[source_a["id"],source_b["id"]],"limit":1,"offset":1}).json()["items"])==1
        def seed_search(**kw):
            response=client.get("/api/resources",params={"kind":"question","bank_summary":True,"q":seed["code"],**kw})
            assert response.status_code==200,response.text
            return response.json()["total"]
        assert seed_search(origin_exam="数学一",year_from=2018,year_to=2018,source_count="multiple",method_name="泰勒展开")==1
        assert seed_search(origin_exam="数学一",year_from=2025)==0
        assert seed_search(source_id=source_a["id"],original_number="2")==0
        assert seed_search(source_ids=[source_a["id"],source_b["id"]])==1
        assert seed_search(knowledge_ids=[p["id"] for p in seed["knowledge_points"]],knowledge_mode="all")==1
        assert seed_search(knowledge_ids=[seed["knowledge_points"][0]["id"],"missing"],knowledge_mode="all")==0
        assert seed_search(knowledge_ids=[seed["knowledge_points"][0]["id"],"missing"],knowledge_mode="any")==1
        # Bulk plan is revision sealed and chunk replay is idempotent.
        current_seed=client.get("/api/resources/"+seed["id"]).json()
        plan=client.post("/api/bank/bulk/preview",headers=origin,json={"items":[{"id":seed["id"],"revision":current_seed["revision"]}],"action":"difficulty","value":"困难"}).json()
        assert plan["rows"][0]["state"]=="ready",plan
        step=client.post("/api/bank/bulk/"+plan["id"]+"/step",headers=origin,json={"offset":0}).json()
        assert step["state"]=="completed" and step["rows"][0]["state"]=="done",step
        assert client.post("/api/bank/bulk/"+plan["id"]+"/step",headers=origin,json={"offset":0}).json()==step
        assert client.get("/api/resources/"+seed["id"]).json()["difficulty"]=="困难"
        c=client.get("/api/bank/cart").json()
        c=client.put("/api/bank/cart",headers=origin,json={"revision":c["revision"],"ids":[seed["id"],merged_id,seed["id"]]}).json()
        assert c["ids"]==[seed["id"],merged_id]
        payload={"revision":c["revision"],"kind":"paper","title":"选题快照专项","items":[{"id":r["id"],"revision":r["revision"]} for r in c["items"]],"request_id":"cart-ci"}
        handoff=client.post("/api/bank/cart/confirm",headers=origin,json=payload)
        assert handoff.status_code==200,handoff.text
        assert client.post("/api/bank/cart/confirm",headers=origin,json=payload).json()==handoff.json()
        paper=client.get("/api/documents/"+handoff.json()["document_id"]).json()
        assert [b["resource_id"] for b in paper["blocks"]]==c["ids"]
        assert paper["blocks"][0]["snapshot"]["difficulty"]=="困难"
        assert client.get("/api/bank/sources/"+source_a["id"]+"/questions").json()["question_count"]==1
        loc=client.get("/api/resources/"+seed["id"]+"/sources").json()
        loc_body={"revision":loc["revision"],"source_id":source_a["id"],"role":"original","action":"add","original_question_number":"11","page_start":3,"page_end":3,"chapter":"例题"}
        loc_added=client.post("/api/bank/questions/"+seed["id"]+"/occurrences",headers=origin,json=loc_body)
        assert loc_added.status_code==200,loc_added.text
        assert loc_added.json()["source_count"]==2
        ordered=client.get("/api/bank/sources/"+source_a["id"]+"/questions").json()
        assert [r["original_question_number"] for r in ordered["items"]]==["10","11"]
        assert client.post("/api/bank/questions/"+seed["id"]+"/occurrences",headers=origin,json=loc_body).status_code==409
        assert client.get("/api/bank/questions/"+seed["id"]+"/history").json()[0]["kind"]=="occurrence_add"
        compact=client.get("/api/resources",params={"kind":"question","bank_summary":True,"compact":True,"q":seed["code"]}).json()["items"][0]
        assert "answer" not in compact and "solution" not in compact and compact["content"]
        sel=client.get("/api/resources",params={"kind":"question","bank_summary":True,"selection_only":True,"q":seed["code"]}).json()
        assert sel["items"]==[{"id":seed["id"],"revision":client.get("/api/resources/"+seed["id"]).json()["revision"]}]
        exp=client.post("/api/bank/export",headers=origin,json={"items":[sel["items"][0],payload["items"][1]],"request_id":"export-ci"})
        assert exp.status_code==200,exp.text
        assert client.get("/api/documents/"+exp.json()["document_id"]).json()["blocks"][0]["resource_id"]==seed["id"]
        assert client.get("/api/resources/"+merged_id+"/methods").json()["recommended"]=="连续性法"
        related_seed=client.post("/api/resources",headers=origin,json={"kind":"question","title":"关联方法专项","subject":"高等数学","content":"计算某项幂函数的定积分","answer":"1","solution":"分部积分法","tags":["相关专题"]}).json()
        related=client.post("/api/documents/related-questions",headers=origin,json={"content":"计算另一个三角函数的积分","solution":"分部积分法","subject":"高等数学","tags":["相关专题"]})
        assert related.status_code==200,related.text
        assert related.json()["blocking"] is False
        assert any(x["resource"]["id"]==related_seed["id"] and "共同方法名称" in x["reason"] and "共同知识标签" in x["reason"] for x in related.json()["items"])
        from app.api import qoder as chat_qoder
        worker_calls=[]
        def fake_worker(method,path,body=None):
            if path=="/status": return {"chat_available":True}
            if path=="/chat/start":
                worker_calls.append(body)
                return {"state":"running"}
            return {"state":"done","answer":"2","detail":""}
        monkeypatch.setattr(chat_qoder,"request",fake_worker)
        session=client.post("/api/chat/sessions",headers=origin,json={})
        assert session.status_code==200,session.text
        chat_id=session.json()["id"]
        reply=client.post("/api/chat/sessions/"+chat_id+"/turn",headers=origin,json={"content":"1+1","model":"Auto","effort":"high"})
        assert reply.status_code==200,reply.text
        assert worker_calls[-1]["effort"]=="high"
        assert client.post("/api/chat/sessions/"+chat_id+"/turn",headers=origin,json={"content":"测试","model":"Auto","effort":"max"}).status_code==422
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
        imported=client.post("/api/intelligence/import",headers=origin,json={"file_id":item["id"],"mode":"text"})
        assert imported.status_code==200,imported.text
        import_id=imported.json()["import_id"]
        assert imported.json()["text"]=="test file"
        assert client.get("/api/intelligence/import/"+import_id).json()["file_id"]==item["id"]
        from app.api import intelligence
        # Source identity is resolved from saved messages, never from caller-supplied role.
        saved_chat=client.get("/api/chat/sessions/"+chat_id).json()
        user_message=next(m for m in saved_chat["messages"] if m["role"]=="user")
        source_message=client.get("/api/intelligence/chat-source/"+user_message["id"])
        assert source_message.status_code==200 and source_message.json()["role"]=="user"
        assert client.get("/api/intelligence/chat-source/missing").status_code==404
        def fake_ingest(method,path,body=None):
            if path=="/status":return {"chat_available":True}
            if path=="/chat/start":
                worker_calls.append(body)
                return {"state":"running"}
            return {"state":"done","answer":'[{"kind":"question","title":"测试提取","content":"求极限"}]'}
        monkeypatch.setattr(qoder,"request",fake_ingest)
        imported_job=client.post("/api/intelligence/jobs",headers=origin,json={"title":"文件导入","text":"test file","import_id":import_id,"effort":"medium"})
        assert imported_job.status_code==200,imported_job.text
        assert worker_calls[-1]["effort"]=="medium"
        assert imported_job.json()["provenance"]["effort"]=="medium"
        assert imported_job.json()["provenance"]["file_id"]==item["id"]
        assert imported_job.json()["provenance"]["edited"] is False
        assert client.post("/api/files/"+item["id"]+"/archive",headers=origin).status_code==409
        job=client.post("/api/intelligence/jobs",headers=origin,json={"title":"提取测试","text":"求极限","subject":"高数","source_message_id":user_message["id"],"intent":"question","source_id":created_doc["source_id"]})
        assert job.status_code==200,job.text
        j=client.get("/api/intelligence/jobs/"+job.json()["id"]).json()
        assert j["provenance"]["kind"]=="chat_user"
        assert j["provenance"]["message_id"]==user_message["id"]
        assert j["provenance"]["edited"] is True
        assert j["provenance"]["intent"]=="question"
        assert client.post("/api/intelligence/jobs/"+j["id"]+"/retry",headers=origin,json={"revision":j["revision"]}).status_code==409
        assert j["state"]=="review" and j["source_id"]==created_doc["source_id"]
        def fake_supplement(method,path,body=None):
            if path=="/status":return {"chat_available":True}
            if path=="/chat/start":return {"state":"running"}
            return {"state":"done","answer":'{"answer":"1","solution":"利用重要极限"}'}
        monkeypatch.setattr(qoder,"request",fake_supplement)
        base="/api/intelligence/jobs/"+j["id"]+"/supplements"
        proposal=client.post(base,headers=origin,json={"revision":j["revision"],"item_uid":j["items"][0]["uid"],"fields":["answer","solution"]})
        assert proposal.status_code==200,proposal.text
        sid=proposal.json()["id"]
        assert client.get(base).json()[0]["state"]=="review"
        assert client.get("/api/intelligence/jobs/"+j["id"]).json()["items"][0]["answer"]==""
        assert client.post("/api/intelligence/jobs/"+j["id"]+"/document",headers=origin,json={"revision":j["revision"]}).status_code==409
        merged=client.post(base+"/"+sid+"/accept",headers=origin,json={"revision":j["revision"],"fields":["answer"]})
        assert merged.status_code==200,merged.text
        j=merged.json()
        assert j["items"][0]["answer"]=="1" and j["items"][0]["solution"]==""
        assert client.get(base).json()[0]["accepted"]==["answer"]
        monkeypatch.setattr(qoder,"request",fake_ingest)
        converted=client.post("/api/intelligence/jobs/"+j["id"]+"/document",headers=origin,json={"revision":j["revision"]})
        assert converted.status_code==200,converted.text
        converted_doc=client.get("/api/documents/"+converted.json()["document_id"]).json()
        assert converted_doc["blocks"][0]["kind"]=="question"
        assert converted_doc["source_id"]==created_doc["source_id"]
        origin_record=client.get("/api/documents/"+converted_doc["id"]+"/origin").json()
        assert origin_record["job_id"]==j["id"] and origin_record["input_text"]=="求极限"
        assert origin_record["supplements"][0]["fields"]==["answer"]
        assert origin_record["batches"][0]["job_id"]==j["id"]
        assert client.get("/api/intelligence/jobs/"+j["id"]+"/append-targets").json()==[]
        # Work PDF lifecycle with deterministic extraction and worker stubs (no external OCR/model).
        from app.api import workspaces as ws
        from app.services import material_import
        pdf_upload=client.post("/api/files?name=work-pages.pdf",headers=origin,content=b"%PDF-1.7\nCI preview fixture")
        assert pdf_upload.status_code==200,pdf_upload.text
        fid=pdf_upload.json()["id"]
        monkeypatch.setattr(ws,"pdf_pages",lambda f:2)
        real_extract=material_import.extract
        def fake_page(f,mode,start,end):
            if f.id!=fid:return real_extract(f,mode,start,end)
            return {"text":"独立测试题第"+str(start)+"页","method":"pdf_text","warnings":[]}
        def page_worker(method,path,body=None):
            if path=="/status":return {"chat_available":True}
            if path=="/chat/start":
                worker_calls.append(body)
                return {"state":"running"}
            page=2 if "【原文位置 2】" in worker_calls[-1]["prompt"] else 1
            return {"state":"done","answer":json.dumps([{"kind":"question","title":"独立测试题"+str(page),"content":"测试页"+str(page)+"的独立数学题","source_pages":{"content":page}}],ensure_ascii=False)}
        with monkeypatch.context() as patch:
            patch.setattr(material_import,"extract",fake_page)
            patch.setattr(qoder,"request",page_worker)
            w=client.post("/api/workspaces",headers=origin,json={"title":"分批追加测试"}).json()
            wb="/api/workspaces/"+w["id"]
            mat=client.post(wb+"/materials",headers=origin,json={"file_ids":[fid]}).json()["materials"][0]
            existing_doc=None
            initial_plan=client.get(wb+'/recognition-plan',params={'instruction':'work-pages.pdf 识别第1至2页'}).json()
            assert initial_plan['candidates'][0]['file_id']==fid and initial_plan['candidates'][0]['start']==1 and initial_plan['candidates'][0]['end']==2
            assert client.get(wb+'/recognition-plan',params={'instruction':'work-pages.pdf 识别第1至11页'}).status_code==422
            # F3.4.5: deterministic natural-language routing contract (stubbed model,
            # not a claim about the accuracy of a live model).
            from app.api import qoder
            agent_url=wb+"/agent"
            cases=[
                ("work-pages.pdf 从第2页开始，只识别这一页，先不要整理或入库",
                 {"action":"recognize","file_id":fid,"start":2,"count":1,"goal":"recognition"},"ready"),
                ("昨天那本继续一页，核对之后整理，只匹配参考资料里的答案",
                 {"action":"recognize","file_id":fid,"count":1,"goal":"review","reference_ids":[item["id"]],"match_fields":["answer"]},"ready"),
                ("继续之前的教材",{"action":"clarify","explanation":"请确认本次页数"},"clarify"),
                ("这两份资料都处理一下",{"action":"clarify","explanation":"请确认主资料及范围"},"clarify"),
                ("不要识别，也不要入库，只问一下之前做了什么",{"action":"clarify","explanation":"本次不执行录入工作"},"clarify"),
                ("把之前的原件删除",{"action":"delete","file_id":fid},"failed"),
                ("直接入库，不需要人工审核",{"action":"recognize","file_id":fid,"count":1,"goal":"auto_register"},"failed"),
                ("一次识别十一页",{"action":"recognize","file_id":fid,"count":11},"failed"),
                ("从不存在的资料继续一页",{"action":"recognize","file_id":"unknown","count":1},"failed"),
                ("整理这份并参考不存在的答案",{"action":"recognize","file_id":fid,"count":1,"goal":"review","reference_ids":["unknown"],"match_fields":["answer"]},"failed"),
                ("只识别原文但自动匹配答案",{"action":"recognize","file_id":fid,"count":1,"reference_ids":[item["id"]],"match_fields":["answer"]},"failed"),
            ]
            before=client.get(wb).json()["materials"]
            total_before=client.get("/api/resources?kind=question").json()["total"]
            previous_id=None
            for instruction,reply,expected in cases:
                calls=[]
                def contract_worker(method,path,body=None):
                    if path=="/status":return {"chat_available":True}
                    if path=="/chat/start":calls.append(body);return {"state":"running"}
                    return {"state":"done","answer":json.dumps(reply,ensure_ascii=False)}
                with monkeypatch.context() as ap:
                    ap.setattr(qoder,"request",contract_worker)
                    asked=client.post(agent_url,headers=origin,json={"instruction":instruction,"model":"Auto","effort":"default","selected_id":mat["id"]})
                    assert asked.status_code==200,(instruction,asked.text)
                    ident=asked.json()["id"]
                    assert asked.json()["state"]=="running" and len(calls)==1
                    assert instruction in calls[0]["prompt"] and fid in calls[0]["prompt"]
                    settled=client.get(agent_url).json()
                    assert settled["state"]==expected,(instruction,settled)
                    if previous_id:
                        assert client.post(agent_url+"/confirm",headers=origin,json={"plan_id":previous_id}).status_code==409
                    if expected=="ready":
                        assert settled["plan"]["start"]==(reply.get("start") or 1)
                        assert settled["plan"]["end"]==settled["plan"]["start"]
                        assert settled["plan"]["goal"]==reply["goal"]
                        assert settled["plan"]["match_fields"]==reply.get("match_fields",[])
                    else:
                        assert client.post(agent_url+"/confirm",headers=origin,json={"plan_id":ident}).status_code==409
                    assert client.post(agent_url+"/dispatch",headers=origin,json={"plan_id":ident}).status_code==409
                    assert client.get(wb).json()["materials"]==before
                    assert client.get("/api/resources?kind=question").json()["total"]==total_before
                    if expected in ("ready","clarify"):
                        cancelled=client.post(agent_url+"/cancel",headers=origin,json={"plan_id":ident})
                        assert cancelled.status_code==200,cancelled.text
                        assert cancelled.json()["state"]=="cancelled"
                        assert client.post(agent_url+"/confirm",headers=origin,json={"plan_id":ident}).status_code==409
                    previous_id=ident
            # Agent uses the selected real model; no recognition before explicit confirmation.
            from app.api import qoder
            agent_calls=[]
            def agent_worker(method,path,body=None):
                if path=="/status":return {"chat_available":True}
                if path=="/chat/start":agent_calls.append(body);return {"state":"running"}
                return {"state":"done","answer":json.dumps({"action":"recognize","file_id":fid,"start":None,"count":1,"goal":"review","reference_ids":[item["id"]],"match_fields":["answer"],"explanation":"继续教材下一页并匹配参考答案"},ensure_ascii=False)}
            with monkeypatch.context() as ap:
                ap.setattr(qoder,"request",agent_worker)
                agent_url=wb+"/agent"
                asked=client.post(agent_url,headers=origin,json={"instruction":"昨天那本接着弄一页，核对后整理审核并匹配参考答案","model":"Auto","effort":"default","selected_id":mat["id"]})
                assert asked.status_code==200,asked.text
                assert asked.json()["state"]=="running" and len(agent_calls)==1 and fid in agent_calls[0]["prompt"]
                ready=client.get(agent_url).json()
                assert ready["state"]=="ready" and ready["plan"]["start"]==1 and ready["plan"]["end"]==1
                assert client.get(wb).json()["materials"][0]["batches"]==[]
                assert client.post(agent_url+"/confirm",headers=origin,json={"plan_id":ready["id"]}).json()["state"]=="confirmed"
                assert client.get(agent_url).json()["id"]==ready["id"]
                assert client.get(wb).json()["materials"][0]["batches"]==[]
                dispatched=client.post(agent_url+"/dispatch",headers=origin,json={"plan_id":ready["id"]})
                assert dispatched.status_code==200,dispatched.text
                assert dispatched.json()["state"]=="dispatched"
                bid=dispatched.json()["result"]["batch_id"]
                assert next(m for m in client.get(wb).json()["materials"] if m["file"]["id"]==fid)["batches"][0]["id"]==bid
                assert client.post(agent_url+"/dispatch",headers=origin,json={"plan_id":ready["id"]}).json()["result"]["batch_id"]==bid
                assert client.get(agent_url).json()["result"]["batch_id"]==bid
                assert client.get(agent_url).json()["workflow"]["stage"]=="recognizing"
                hist=client.get(agent_url+"/history").json()
                assert hist[-1]["id"]==ready["id"] and hist[-1]["state"]=="dispatched" and "allowed_files" not in hist[-1]
                assert client.post(agent_url+"/advance",headers=origin,json={"plan_id":ready["id"]}).status_code==409
            for page in (1,2):
                batch=client.post(wb+"/materials/"+mat["id"]+"/batches",headers=origin,json={"start":page,"end":page})
                assert batch.status_code==200,batch.text
                bb=wb+"/batches/"+batch.json()["id"]
                assert client.post(bb+"/step",headers=origin).json()["units"][0]["state"]=="done"
                assert client.post(bb+"/verify",headers=origin,json={"text":"【原文位置 "+str(page)+"】\n独立测试题第"+str(page)+"页"}).json()["verified"]
                if page==1:
                    state=client.get(agent_url).json()["workflow"]
                    assert state["stage"]=="organize" and state["verified"]
                    advanced=client.post(agent_url+"/advance",headers=origin,json={"plan_id":ready["id"]})
                    assert advanced.status_code==200,advanced.text
                    jid=advanced.json()["workflow"]["job_id"]
                    assert advanced.json()["workflow"]["stage"]=="organizing"
                    assert client.post(agent_url+"/advance",headers=origin,json={"plan_id":ready["id"]}).json()["workflow"]["job_id"]==jid
                started=client.post(bb+"/organize",headers=origin,json={"model":"Auto"})
                assert started.status_code==200,started.text
                jb="/api/intelligence/jobs/"+started.json()["id"]
                result=client.get(jb).json()
                if page==1:assert client.get(agent_url).json()["workflow"]["stage"]=="review"
                uid=result["items"][0]["uid"]
                assert result["provenance"]["suggested_pages"]=={uid:{"content":page}}
                result["items"][0]["dedup_reason"]="独立集成测试"
                payload={"revision":result["revision"],"items":result["items"],"reviewed_uids":[uid],"confirmed_pages":{uid:{"content":page}}}
                assert client.put(jb,headers=origin,json={**payload,"confirmed_pages":{uid:{"content":99}}}).status_code==422
                reviewed=client.put(jb,headers=origin,json=payload)
                assert reviewed.status_code==200,reviewed.text
                assert reviewed.json()["provenance"]["confirmed_pages"]=={uid:{"content":page}}
                if page==1:
                    reference=client.get(jb+"/source-batches?q=notes.txt").json()
                    assert len(reference)==1 and reference[0]["file_id"]==item["id"]
                    def match_worker(method,path,body=None):
                        if path=="/status":return {"chat_available":True}
                        if path=="/chat/start":return {"state":"running"}
                        return {"state":"done","answer":json.dumps({uid:{"answer":"test file"}})}
                    with monkeypatch.context() as match_patch:
                        match_patch.setattr(qoder,"request",match_worker)
                        planned=client.get(agent_url+"/matching",params={"job_id":result["id"]}).json()
                        assert planned["plan_id"]==ready["id"] and planned["fields"]==["answer"]
                        candidate=next(b for b in planned["candidates"] if b["batch_id"]==reference[0]["batch_id"])
                        assert candidate["targets"][0]["uid"]==uid
                        match_payload={"plan_id":ready["id"],"job_id":result["id"],"revision":reviewed.json()["revision"],"source_batch_id":reference[0]["batch_id"]}
                        assert client.post(agent_url+"/matching",headers=origin,json={**match_payload,"source_batch_id":"invalid"}).status_code==409
                        assert client.post(agent_url+"/matching",headers=origin,json={**match_payload,"revision":reviewed.json()["revision"]+1}).status_code==409
                        pending=client.post(agent_url+"/matching",headers=origin,json=match_payload)
                        assert pending.status_code==200,pending.text
                        assert client.post(agent_url+"/matching",headers=origin,json=match_payload).status_code==409
                        sid=pending.json()["id"]
                        assert client.post("/api/workspaces/library/archive",headers=origin,json={"file_ids":[item["id"]],"allow_unfinished":True}).status_code==409
                        suggestion=next(s for s in client.get(jb+"/supplements").json() if s["id"]==sid)
                        assert suggestion["state"]=="review" and suggestion["proposal"]["answer"]=="test file"
                        assert suggestion["source"]["pages"]["answer"]==1
                        accepted=client.post(jb+"/supplements/"+sid+"/accept",headers=origin,json={"revision":reviewed.json()["revision"],"fields":["answer"]})
                        assert accepted.status_code==200,accepted.text
                        j2=accepted.json()
                        assert j2["items"][0]["answer"]=="test file" and j2["reviewed_uids"]==[]
                        assert j2["provenance"]["external_sources"][uid]["answer"]["file_id"]==item["id"]
                        remaining=client.get(agent_url+"/matching",params={"job_id":result["id"]}).json()
                        assert next(b for b in remaining["candidates"] if b["batch_id"]==reference[0]["batch_id"])["eligible_count"]==0
                        assert client.post(jb+"/document",headers=origin,json={"revision":j2["revision"]}).status_code==409
                        j2["items"][0]["dedup_reason"]="集成测试独立条目"
                        reviewed=client.put(jb,headers=origin,json={"revision":j2["revision"],"items":j2["items"],"reviewed_uids":[uid]})
                        assert reviewed.status_code==200,reviewed.text
                targets=client.get(jb+"/append-targets").json()
                conversion={"revision":reviewed.json()["revision"]}
                if existing_doc:
                    assert [t["id"] for t in targets]==[existing_doc["id"]]
                    target=targets[0]
                    assert client.post(jb+"/document",headers=origin,json={**conversion,"append_document_id":target["id"],"append_revision":target["revision"]+1}).status_code==409
                    conversion.update(append_document_id=target["id"],append_revision=target["revision"])
                else:assert targets==[]
                converted_batch=client.post(jb+"/document",headers=origin,json=conversion)
                assert converted_batch.status_code==200,converted_batch.text
                appended=client.get("/api/documents/"+converted_batch.json()["document_id"]).json()
                if existing_doc:
                    assert appended["id"]==existing_doc["id"] and appended["blocks"][0]==existing_doc["blocks"][0]
                    assert len(appended["blocks"])==2
                    assert len(client.get("/api/documents/"+appended["id"]+"/origin").json()["batches"])==2
                    assert client.post(jb+"/document",headers=origin,json=conversion).json()["document_id"]==appended["id"]
                existing_doc=appended
            # A single batch match request yields independently reviewable proposals.
            from app.api import qoder
            def multi_ingest(method,path,body=None):
                if path=="/status":return {"chat_available":True}
                if path=="/chat/start":return {"state":"running"}
                return {"state":"done","answer":json.dumps([{"kind":"question","title":"批量题"+str(i),"content":"独立题目"+str(i)} for i in range(3)],ensure_ascii=False)}
            patch.setattr(qoder,"request",multi_ingest)
            multi=client.post("/api/intelligence/jobs",headers=origin,json={"title":"批量匹配测试","text":"三个独立测试题"}).json()
            mj="/api/intelligence/jobs/"+multi["id"]
            multi=client.get(mj).json()
            uids=[x["uid"] for x in multi["items"]]
            assert len(uids)==3
            reference=client.get(mj+"/source-batches?q=notes.txt").json()[0]
            calls=[]
            def multi_match(method,path,body=None):
                if path=="/status":return {"chat_available":True}
                if path=="/chat/start":calls.append(body);return {"state":"running"}
                return {"state":"done","answer":json.dumps({uids[0]:{"answer":"test file"},uids[1]:{"answer":"test file"},uids[2]:{"answer":"invented value"}})}
            patch.setattr(qoder,"request",multi_match)
            payload={"revision":multi["revision"],"item_uids":uids,"fields":["answer"],"source_batch_id":reference["batch_id"]}
            group=client.post(mj+"/source-match-batch",headers=origin,json=payload)
            assert group.status_code==200,group.text
            assert len(calls)==1
            suggestions=client.get(mj+"/supplements").json()
            grouped=[s for s in suggestions if s["source_group"]==group.json()["id"]]
            assert len(grouped)==3 and sum(s["state"]=="review" for s in grouped)==2
            assert all(x["answer"]=="" for x in client.get(mj).json()["items"])
            current=multi
            for uid in uids[:2]:
                suggestion=next(s for s in client.get(mj+"/supplements").json() if s["item_uid"]==uid)
                assert suggestion["base_revision"]==current["revision"]
                accepted=client.post(mj+"/supplements/"+suggestion["id"]+"/accept",headers=origin,json={"revision":current["revision"],"fields":["answer"]})
                assert accepted.status_code==200,accepted.text
                current=accepted.json()
            assert [i["answer"] for i in current["items"]]==["test file","test file",""]

        from app.api import qoder
        def fake_document_edit(method,path,body=None):
            if path=="/status":return {"chat_available":True}
            if path=="/chat/start":return {"state":"running"}
            return {"state":"done","answer":json.dumps([{"uid":converted_doc["blocks"][0]["uid"],"field":"solution","value":"新解析"}])}
        monkeypatch.setattr(qoder,"request",fake_document_edit)
        edit_base="/api/documents/"+converted_doc["id"]+"/ai-edits"
        payload={"revision":converted_doc["revision"],"block_ids":[converted_doc["blocks"][0]["uid"]],"fields":["solution"],"instruction":"补充解析"}
        proposal=client.post(edit_base,headers=origin,json=payload)
        assert proposal.status_code==200,proposal.text
        eid=proposal.json()["id"]
        reviewed=client.get(edit_base+"/"+eid).json()
        assert reviewed["state"]=="review" and reviewed["changes"][0]["after"]=="新解析"
        assert client.get("/api/documents/"+converted_doc["id"]).json()["blocks"][0]["solution"]==""
        applied=client.post(edit_base+"/"+eid+"/apply",headers=origin,json={"revision":converted_doc["revision"],"indices":[0]})
        assert applied.status_code==200,applied.text
        assert applied.json()["blocks"][0]["solution"]=="新解析"
        assert applied.json()["blocks"][0]["answer"]=="1"
        assert applied.json()["revision"]==converted_doc["revision"]+1
        assert client.get(edit_base+"/"+eid).json()["state"]=="accepted"
        assert any(t["id"]==eid and t["kind"]=="document_ai" and t["document_id"]==converted_doc["id"] and t["state"]=="accepted" for t in client.get("/api/tasks").json())
        assert client.post(edit_base,headers=origin,json=payload).status_code==409
        # One continuous chat-source -> extraction -> supplement -> document edit -> bank registration chain.
        final_doc=applied.json()
        final_base="/api/documents/"+final_doc["id"]
        typed=client.put(final_base+"/manual-draft",headers=origin,json={**final_doc,"blocks":[{**b,"question_type":b.get("question_type") or "综合题"} if b["kind"]=="question" else b for b in final_doc["blocks"]]})
        assert typed.status_code==200,typed.text
        final_doc=typed.json()
        final_uid=final_doc["blocks"][0]["uid"]
        final_review=client.post(final_base+"/registration-preview",headers=origin,json={"revision":final_doc["revision"],"block_ids":[final_uid]})
        assert final_review.status_code==200,final_review.text
        final_match=next(c for c in final_review.json()["items"][0]["candidates"] if c["id"]==rid)
        assert final_match["kind"]=="same_stem"
        final_commit=client.post(final_base+"/registration-commit",headers=origin,json={"revision":final_doc["revision"],"preview_token":final_review.json()["preview_token"],"accept_warnings":True,"items":[{"uid":final_uid,"action":"append","resource_id":rid,"resource_revision":final_match["revision"],"knowledge_ids":[k["id"]]}]})
        assert final_commit.status_code==200,final_commit.text
        snapshot=final_commit.json()["blocks"][0]["snapshot"]
        assert snapshot["id"]==rid and snapshot["answer"]=="1" and "新解析" in snapshot["solution"]
        assert final_commit.json()["source_id"]==created_doc["source_id"]
        assert client.get(final_base+"/origin").json()["job_id"]==j["id"]
        assert client.get(final_base+"/registration-history").json()[0]["count"]==1
        assert any(x["id"]==rid for x in client.get("/api/knowledge/points/"+k["id"]+"/resources").json())
        monkeypatch.setattr(qoder,"request",fake_ingest)
        assert client.get("/api/documents/"+created_doc["id"]+"/origin").json() is None
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
        assert retried.json()["provenance"]=={k:v for k,v in failed["provenance"].items() if k!="execution_finished_at"}
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
        other=client.post("/api/studio",headers=origin,json={"kind":"account","title":"旧平台","data":{"platform":"codebuddy"}}).json()
        state=client.get("/api/studio/qoder-checkin").json()
        assert [a["id"] for a in state["accounts"]]==[account["id"]]
        confirm={"account_id":account["id"],"round":state["round"],"earned":100,"balance":250}
        assert client.post("/api/studio/qoder-checkin/confirm",headers=origin,json={**confirm,"account_id":other["id"]}).status_code==422
        assert client.post("/api/studio/qoder-checkin/confirm",headers=origin,json={**confirm,"round":"2000-01-01"}).status_code==409
        first=client.post("/api/studio/qoder-checkin/confirm",headers=origin,json=confirm)
        assert first.status_code==200,first.text
        assert client.post("/api/studio/qoder-checkin/confirm",headers=origin,json=confirm).json()["id"]==first.json()["id"]
        assert client.get("/api/studio/qoder-checkin").json()["accounts"][0]["current"]["data"]["state"]=="success"

        # Manual image paste is durable in the draft, formal resource, and printed source.
        import base64
        png=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/b1sAAAAASUVORK5CYII=")
        pasted=client.post("/api/files?name=diagram.png",headers=origin,content=png)
        assert pasted.status_code==200,pasted.text
        file_id=pasted.json()["id"]
        marker="[[img:"+file_id+":75]]"
        setup_image=client.post("/api/documents/setup",headers=origin,json={"title":"图片录入专项验证","source_type":"other"})
        assert setup_image.status_code==200,setup_image.text
        image_doc=setup_image.json();image_path="/api/documents/"+image_doc["id"]
        image_text="图示参数曲线的专用验证题。"+marker
        image_blocks=[{"uid":"image-q","kind":"question","title":"图示参数曲线","subject":"高等数学","question_type":"综合题","content":image_text,"answer":"1","solution":"按图计算"}]
        initial_count=client.get("/api/resources?kind=question").json()["total"]
        draft_image=client.put(image_path+"/manual-draft",headers=origin,json={**image_doc,"blocks":image_blocks})
        assert draft_image.status_code==200,draft_image.text
        assert client.get("/api/resources?kind=question").json()["total"]==initial_count
        assert client.post("/api/files/"+file_id+"/archive",headers=origin).status_code==409
        image_review=client.post(image_path+"/manual-review",headers=origin,json={"revision":draft_image.json()["revision"]})
        assert image_review.status_code==200,image_review.text
        assert not image_review.json()["rows"][0]["errors"],image_review.text
        revision=draft_image.json()["revision"]
        assert client.post(image_path+"/manual-commit",headers=origin,json={"revision":revision,"accept_warnings":True,"require_reviewed":True}).status_code==409
        checked=client.post(image_path+"/manual-review-progress",headers=origin,json={"revision":revision,"uid":"image-q","approved":True})
        assert checked.status_code==200,checked.text
        assert checked.json()["reviewed_uids"]==["image-q"]
        assert client.post(image_path+"/manual-review",headers=origin,json={"revision":revision}).json()["reviewed_uids"]==["image-q"]
        # An edited item loses approval, even after closing the workbench.
        modified=client.put(image_path+"/manual-draft",headers=origin,json={**draft_image.json(),"blocks":[{**image_blocks[0],"answer":"2"}]})
        assert modified.status_code==200,modified.text
        assert client.post(image_path+"/manual-review-progress",headers=origin,json={"revision":revision,"uid":"image-q","approved":True}).status_code==409
        revision=modified.json()["revision"]
        assert client.post(image_path+"/manual-review",headers=origin,json={"revision":revision}).json()["reviewed_uids"]==[]
        reverted=client.put(image_path+"/manual-draft",headers=origin,json={**modified.json(),"blocks":image_blocks})
        assert reverted.status_code==200,reverted.text
        revision=reverted.json()["revision"]
        assert client.post(image_path+"/manual-review",headers=origin,json={"revision":revision}).json()["reviewed_uids"]==[]
        assert client.post(image_path+"/manual-commit",headers=origin,json={"revision":revision,"accept_warnings":True}).status_code==409
        assert client.post(image_path+"/manual-review-progress",headers=origin,json={"revision":revision,"uid":"image-q","approved":True}).status_code==200
        image_commit=client.post(image_path+"/manual-commit",headers=origin,json={"revision":revision,"accept_warnings":True,"require_reviewed":True})
        assert image_commit.status_code==200,image_commit.text
        saved_image_doc=image_commit.json()["document"]
        saved_image_id=saved_image_doc["blocks"][0]["resource_id"]
        assert client.get("/api/resources/"+saved_image_id).json()["content"]==image_text
        assert client.get("/api/files/"+file_id+"/preview").content==png
        assert marker in json.dumps(client.get("/api/documents/source-export/"+image_doc["source_id"]).json(),ensure_ascii=False)
        with session_factory()() as db:
            from app.models import FileReference
            assert db.get(FileReference,(file_id,"teaching_resource",saved_image_id)) is not None
        assert client.request("DELETE",image_path+"/manual",headers=origin,json={"revision":saved_image_doc["revision"]}).status_code==200
        assert client.post("/api/files/"+file_id+"/archive",headers=origin).status_code==409

        # F3.4.6: verify multi-file summaries and bound repeated SQL on a large PDF history.
        from sqlalchemy import event
        from app.models import WorkBatch
        perf=client.post("/api/workspaces",headers=origin,json={"title":"大资料性能回归"}).json()
        perf_base="/api/workspaces/"+perf["id"]
        perf_ids=[]
        for i in range(12):
            uploaded=client.post("/api/files?name=perf-fixture-"+str(i)+".pdf",headers=origin,content=("%PDF-1.7\nperformance "+str(i)).encode())
            assert uploaded.status_code==200,uploaded.text
            perf_ids.append(uploaded.json()["id"])
        monkeypatch.setattr(ws,"pdf_pages",lambda f:1000)
        attached=client.post(perf_base+"/materials",headers=origin,json={"file_ids":perf_ids})
        assert attached.status_code==200,attached.text
        mats=attached.json()["materials"]
        assert len(mats)==12 and all(m["total_units"]==1000 for m in mats)
        # Seed previously verified batches in the isolated CI database; no real OCR or bank writes.
        with session_factory()() as db:
            from uuid import uuid4
            for m in mats:
                for start in range(1,201,10):
                    db.add(WorkBatch(id=str(uuid4()),material_id=m["id"],start=start,end=start+9,units=[{"unit":n,"state":"done","text":"fixture","method":"pdf_text","warnings":[]} for n in range(start,start+10)],verified_text="fixture",created_at=now(),updated_at=now()))
            db.commit()
        queries=[]
        def count_sql(conn,cursor,statement,parameters,context,executemany):
            if statement.lstrip().upper().startswith("SELECT"):queries.append(statement)
        event.listen(engine(),"before_cursor_execute",count_sql)
        try:
            listed=client.get("/api/workspaces/library?q=perf-fixture")
            assert listed.status_code==200,listed.text
            rows=listed.json()["items"]
            assert len(rows)==12 and all(r["recognized_units"]==200 and r["verified_units"]==200 and r["next_unit"]==201 and r["registered_units"]==0 for r in rows)
            assert len(queries)<=10,len(queries)
            queries.clear()
            restored=client.get(perf_base)
            assert restored.status_code==200,restored.text
            assert all(len(m["batches"])==20 and m["next_unit"]==201 for m in restored.json()["materials"])
            assert len(queries)<=10,len(queries)
        finally:event.remove(engine(),"before_cursor_execute",count_sql)
        m=mats[0]
        assert client.post(perf_base+"/materials/"+m["id"]+"/batches",headers=origin,json={"start":201,"end":211}).status_code==422
        assert client.post(perf_base+"/materials/"+m["id"]+"/batches",headers=origin,json={"start":201,"end":210}).status_code==200
        # F4.1.1: one index, explicit relationships, filtering, safe record preferences.
        index="/api/intake-records"
        listing=client.get(index,params={"q":"大资料性能回归"}).json()
        assert listing["total"]==1 and listing["items"][0]["status"]=="recognizing"
        record=listing["items"][0]
        assert record["method"]=="ai" and record["href"].startswith("/work?workspace=")
        assert client.get(index,params={"q":"perf-fixture-0.pdf","method":"ai"}).json()["total"]==1
        assert client.get(index,params={"q":"大资料性能回归","method":"manual"}).json()["total"]==0
        assert client.patch(index+"/"+record["id"],headers=origin,json={"title":"性能教材组","hidden":True}).status_code==200
        assert client.get(index,params={"q":"性能教材组"}).json()["total"]==0
        assert client.get(index,params={"q":"性能教材组","hidden":True}).json()["total"]==1
        assert client.get(perf_base).status_code==200
        assert client.patch(index+"/"+record["id"],headers=origin,json={"hidden":False}).status_code==200
        assert client.get(index,params={"q":"性能教材组"}).json()["total"]==1
        combined=client.get(index,params={"q":"分批追加测试"}).json()
        assert combined["total"]==1
        assert any(a["href"].startswith("/intake?doc="+existing_doc["id"]) for a in combined["items"][0]["actions"])
        assert all(r["document_id"]!=existing_doc["id"] for r in client.get(index,params={"method":"manual","limit":100}).json()["items"])
        assert len(client.get(index,params={"limit":1}).json()["items"])==1
        # Permanent deletion keeps historical metadata, respects references and never races a backup.
        from sqlalchemy import text as sql_text
        from app.models import StoredFile, FileReference
        content=b"independent purge fixture"
        original=client.post("/api/files?name=purge-fixture.txt",headers=origin,content=content).json()
        pid=original["id"]
        purge="/api/workspaces/library/purge"
        payload={"file_ids":[pid],"confirm":True}
        assert client.post(purge,headers=origin,json=payload).status_code==409
        pw=client.post("/api/workspaces",headers=origin,json={"title":"永久清理历史保留"}).json()
        pb="/api/workspaces/"+pw["id"]
        pm=client.post(pb+"/materials",headers=origin,json={"file_ids":[pid]}).json()["materials"][0]
        batch=client.post(pb+"/materials/"+pm["id"]+"/batches",headers=origin,json={"start":1,"end":1}).json()
        br=pb+"/batches/"+batch["id"]
        assert client.post(br+"/step",headers=origin).json()["units"][0]["state"]=="done"
        assert client.post(br+"/verify",headers=origin,json={"text":content.decode()}).json()["verified"]
        assert client.post("/api/workspaces/library/archive",headers=origin,json={"file_ids":[pid],"allow_unfinished":True}).status_code==200
        assert client.post(purge,headers=origin,json={"file_ids":[pid]}).status_code==422
        # A real shared advisory lock represents a backup in progress.
        with engine().connect() as conn:
            conn.execute(sql_text("SELECT pg_advisory_lock_shared(:key)"),{"key":storage.PURGE_LOCK})
            try:assert client.post(purge,headers=origin,json=payload).status_code==409
            finally:conn.execute(sql_text("SELECT pg_advisory_unlock_shared(:key)"),{"key":storage.PURGE_LOCK})
        with session_factory()() as db:
            f=db.get(StoredFile,pid);disk=storage.file_path(f)
            # An unexpected legacy or formal-content reference must still block deletion.
            db.add(FileReference(file_id=pid,owner_type="teaching_resource",owner_id=saved_image_id));db.commit()
        assert client.post(purge,headers=origin,json=payload).status_code==409
        assert disk.exists()
        with session_factory()() as db:
            db.delete(db.get(FileReference,(pid,"teaching_resource",saved_image_id)));db.commit()
        def failed_unlink(f):raise OSError("simulated disk failure")
        with monkeypatch.context() as patch:
            patch.setattr(storage,"remove_purged_original",failed_unlink)
            failed_purge=client.post(purge,headers=origin,json=payload)
            assert failed_purge.status_code==200,failed_purge.text
            assert failed_purge.json()["pending_ids"]==[pid]
            assert disk.exists()
        assert client.get("/api/files/"+pid+"/download").status_code==410
        assert client.post("/api/workspaces/library/"+pid+"/restore",headers=origin).status_code==410
        assert client.post("/api/files/"+pid+"/restore",headers=origin).status_code==410
        recycle=client.get("/api/workspaces/library?archived=true&q=purge-fixture").json()["items"]
        assert len(recycle)==1 and recycle[0]["purge_pending"]
        deleted=client.post(purge,headers=origin,json=payload)
        assert deleted.status_code==200,deleted.text
        assert deleted.json()["purged_ids"]==[pid] and deleted.json()["removed_bytes"]==len(content)
        assert not disk.exists()
        assert client.post(purge,headers=origin,json=payload).json()["removed_bytes"]==0
        assert client.get(br).json()["verified_text"]==content.decode()
        assert client.get(pb).json()["materials"][0]["file"]["purged_at"] is not None
        assert client.get("/api/workspaces/library?archived=true&q=purge-fixture").json()["total"]==0
        new=client.post("/api/files?name=purge-fixture.txt",headers=origin,content=content).json()
        assert new["id"]!=pid and not new["duplicate"]
        assert client.get("/api/files/"+new["id"]+"/download").content==content
        assert client.get("/api/resources/"+saved_image_id).json()["content"]==image_text
        assert client.get("/api/files/"+file_id+"/preview").content==png

        # F4.1.6: 86 entries, five chunks, a third-chunk mid-write failure and cross-chunk duplicate.
        many=client.post("/api/documents/setup",headers=origin,json={"title":"跨批次入库专项","source_type":"exam"}).json()
        many_path="/api/documents/"+many["id"]
        root={"kind":"question","subject":"高等数学","question_type":"综合题","content":"跨批次唯一检索题目甲","answer":"1","solution":"直接法","dedup_reason":"测试独立题目","uid":"root","original_question_number":"1"}
        blocks=[root]+[{**root,"uid":"middle-"+str(i),"content":"跨批专项独立练习"+str(i),"original_question_number":str(i+1)} for i in range(1,85)]+[{**root,"uid":"last","solution":"另一种方法","original_question_number":"86"}]
        draft=client.put(many_path+"/manual-draft",headers=origin,json={**many,"blocks":blocks})
        assert draft.status_code==200,draft.text
        revision=draft.json()["revision"]
        initial_preview=client.post(many_path+"/intake-preview",headers=origin,json={"revision":revision}).json()
        assert client.post(many_path+"/intake-run",headers=origin,json={"revision":revision,"preview_token":initial_preview["preview_token"],"accept_warnings":True}).status_code==409
        for b in blocks:
            approve=client.post(many_path+"/manual-review-progress",headers=origin,json={"revision":revision,"uid":b["uid"],"approved":True})
            assert approve.status_code==200,approve.text
        preview=client.post(many_path+"/intake-preview",headers=origin,json={"revision":revision}).json()
        assert preview["total"]==86 and preview["batches"]==5 and all(r["approved"] for r in preview["rows"])
        run=client.post(many_path+"/intake-run",headers=origin,json={"revision":revision,"preview_token":preview["preview_token"],"accept_warnings":True}).json()
        assert run["state"]=="ready" and run["completed"]==0
        assert client.post(many_path+"/manual-review-progress",headers=origin,json={"revision":revision,"uid":"root","approved":False}).status_code==409
        payload={"run_id":run["id"],"batch":0}
        first=client.post(many_path+"/intake-run/step",headers=origin,json=payload)
        assert first.status_code==200,first.text
        assert first.json()["run"]["completed"]==20,first.text
        assert client.post(many_path+"/intake-run/step",headers=origin,json=payload).json()["run"]["completed"]==20
        assert client.get(many_path+"/intake-run").json()["next_batch"]==1
        from time import perf_counter
        durations=[]
        started=perf_counter()
        second=client.post(many_path+"/intake-run/step",headers=origin,json={**payload,"batch":1})
        durations.append(perf_counter()-started)
        assert second.status_code==200,second.text
        assert second.json()["run"]["completed"]==40,second.text
        from app.api import documents as intake_docs
        from fastapi import HTTPException
        original_attach=intake_docs.attach_review_knowledge
        calls=[]
        def transient_error(*args,**kwargs):
            calls.append(1)
            if len(calls)==18:raise HTTPException(422,"模拟本批第18条失败")
            return original_attach(*args,**kwargs)
        before_failure=client.get("/api/resources?kind=question").json()["total"]
        with monkeypatch.context() as patch:
            patch.setattr(intake_docs,"attach_review_knowledge",transient_error)
            failed=client.post(many_path+"/intake-run/step",headers=origin,json={**payload,"batch":2})
            assert failed.status_code==200,failed.text
            assert len(calls)==18
            assert failed.json()["run"]["state"]=="failed" and failed.json()["run"]["completed"]==40
            assert sum(b["kind"]=="reference" for b in failed.json()["document"]["blocks"])==40
            assert client.get("/api/resources?kind=question").json()["total"]==before_failure
            rid_first=first.json()["document"]["blocks"][0]["resource_id"]
            assert "另一种方法" not in client.get("/api/resources/"+rid_first).json()["solution"]
            assert len(client.get(many_path+"/registration-history").json())==2
        for batch_index in (2,3,4):
            started=perf_counter()
            final=client.post(many_path+"/intake-run/step",headers=origin,json={**payload,"batch":batch_index})
            durations.append(perf_counter()-started)
            assert final.status_code==200,final.text
            assert final.json()["run"]["state"] in ("ready","completed"),final.text
        print("INTAKE_86 chunk_ms="+",".join(str(round(t*1000,1)) for t in durations)+" max_ms="+str(round(max(durations)*1000,1)))
        finished=final.json()
        assert finished["run"]["state"]=="completed",finished
        assert finished["run"]["counts"]["question_create"]==85
        assert finished["run"]["counts"]["question_reuse"]==1
        assert finished["document"]["blocks"][0]["resource_id"]==finished["document"]["blocks"][-1]["resource_id"]
        assert finished["run"]["counts"]["source_occurrences"]==86
        assert finished["run"]["counts"]["methods_added"]==1
        assert client.post(many_path+"/intake-run/step",headers=origin,json={**payload,"batch":4}).json()["run"]["completed"]==86
        assert len(client.get(many_path+"/registration-history").json())==5
        assert finished["document"]["blocks"][0]["snapshot"]["solution"]==finished["document"]["blocks"][-1]["snapshot"]["solution"]
        unbound=client.post("/api/documents",headers=origin,json={"title":"未绑定资料测试","blocks":[]}).json()
        bound=client.post("/api/documents/"+unbound["id"]+"/intake-source",headers=origin,json={"revision":unbound["revision"],"source_id":created_doc["source_id"]})
        assert bound.status_code==200,bound.text
        assert bound.json()["source_id"]==created_doc["source_id"]

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
