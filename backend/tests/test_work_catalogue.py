from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api import teaching_works as api
from app.models import User, TeachingWork, TeachingWorkVersion, StudioItem, VideoProject, WorkHandoff


def test_catalogue_combines_real_video_records_and_documents():
    engine = create_engine("sqlite://")
    for model in (User, TeachingWork, TeachingWorkVersion, StudioItem, VideoProject, WorkHandoff):
        model.__table__.create(engine)
    with Session(engine) as db:
        db.add(User(id=1, username="test", password_hash="test", created_at=1))
        db.add(TeachingWork(id="w", user_id=1, origin_scope="doc", origin_id="d", variant="v",
                            kind="paper", title="数学试卷", subject="高等数学", current_version=1,
                            created_at=10, updated_at=20))
        db.add(TeachingWorkVersion(work_id="w",number=1,fingerprint="x",snapshot={},facets={"knowledge_points":["极限"],"knowledge_tags":["数列"],"institutions":["郑州大学"],"years":["2026"],"subjects":["高等数学","线性代数"]},created_at=10))
        db.add(StudioItem(id="s",kind="work",title="数学视频",data={"category":"video"},
                          revision=1,archived=False,created_at=5,updated_at=30))
        db.add(StudioItem(id="old",kind="work",title="未归档引擎视频",data={"category":"video"},
                          revision=1,archived=False,created_at=5,updated_at=40))
        db.add(VideoProject(id="p",resource_id="r",resource_revision=1,
                            source_snapshot={"subject":"高等数学"},engine_id="e",work_id="s",created_at=5))
        db.commit()
        user=db.get(User,1)
        def query(**kwargs):
            return api.listing(**({"q":"","kind":"","subject":"","scope":"","sort":"recent",
                                  "created_from":None,"created_to":None,"offset":0,"limit":20,
                                  "db":db,"user":user}|kwargs))
        assert [w["id"] for w in query()["items"]]==["s","w"]
        assert query(kind="video")["total"]==1
        assert query(subject="高等数学",q="数学")["total"]==2
        assert query(scope="doc")["items"][0]["id"]=="w"
        assert query(sort="old",limit=1,offset=1)["items"][0]["id"]=="w"
        assert api.subjects(db=db,user=user)==["高等数学"]
        assert query(institution="郑州大学",year="2026",knowledge_point="极限")["total"]==1
        assert query(knowledge_tag="极限")["total"]==0
        assert query(subjects_all="高等数学,线性代数")["total"]==1
        detail=api.detail("s",db=db,user=user)
        assert detail["video"]["project_id"]=="p" and detail["current_version"] is None


def test_snapshot_knowledge_names_are_not_graph_labels():
    snapshot={"doc":{"blocks":[
        {"kind":"heading","title":"第一章"},
        {"kind":"reference","uid":"q1","resource_id":"r","local_fields":["content"],"content":"修改后",
         "snapshot":{"kind":"question","title":"题目","content":"原题","tags":["录入知识点"],
                     "knowledge_tags":[{"id":"k","name":"图谱标签"}],"source_id":"s"}},
        {"kind":"question","uid":"q2","content":"自编题","knowledge_tags":["手工知识点"]}
    ]}}
    first,second=api.snapshot_questions(snapshot)
    assert first["content"]=="修改后"
    assert first["chapter"]=="第一章"
    assert first["knowledge_points"]==["录入知识点"]
    assert first["knowledge_tags"]==["图谱标签"]
    assert second["knowledge_points"]==["手工知识点"] and second["knowledge_tags"]==[]
