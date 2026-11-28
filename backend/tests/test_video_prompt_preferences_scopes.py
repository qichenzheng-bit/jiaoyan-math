from types import SimpleNamespace
from app.core import ai_preferences as prefs


def test_scoped_video_supplements(monkeypatch):
    prompts={"video":"公共视频","video_question":"例题专属","video_knowledge":"知识单元专属",
             "video_knowledge_with_proof":"含证明专属","video_knowledge_without_proof":"无证明专属"}
    monkeypatch.setattr(prefs,"prompt",lambda db,user,scope:{"text":prompts.get(scope,""),"revision":1})
    monkeypatch.setattr(prefs,"memories",lambda db,user:{"items":[]})
    user=SimpleNamespace(id=1)
    question=prefs.video_supplement(None,user)["text"]
    proof=prefs.video_supplement(None,user,business="knowledge",teaching_type="with_proof")["text"]
    no_proof=prefs.video_supplement(None,user,business="knowledge",teaching_type="without_proof")["text"]
    auto_data=prefs.video_supplement(None,user,business="knowledge")
    auto=auto_data["text"]
    assert "含证明专属" in auto_data["resolved_supplements"]["with_proof"]
    assert "无证明专属" not in auto_data["resolved_supplements"]["with_proof"]
    assert "含证明专属" not in auto_data["resolved_supplements"]["without_proof"]
    assert "例题专属" in question and "知识单元专属" not in question
    assert "知识单元专属" in proof and "含证明专属" in proof and "无证明专属" not in proof
    assert "无证明专属" in no_proof and "含证明专属" not in no_proof
    assert "例题专属" not in auto and "仅当实际教学类型" in auto
    assert all("公共视频" in p for p in (question,proof,no_proof,auto))
    prompts["video_knowledge_with_proof"]="新的证明要求"
    assert prefs.video_supplement(None,user)["text"] == question
    assert prefs.video_supplement(None,user,business="knowledge",teaching_type="without_proof")["text"] == no_proof
