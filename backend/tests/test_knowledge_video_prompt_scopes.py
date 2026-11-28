import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("knowledge_prompt_bundle", ROOT / "vendor/video-overlay/app/backend/src/weiguang_backend/pipeline/prompt_bundle.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)

def capture(kind, teaching_type="auto"):
    meta = {"source_context":{"business_type":kind,"teaching_type":teaching_type}}
    return bundle.capture_rules(meta, "极限", "证明", "资料")

def test_scoped_rules(monkeypatch):
    before = [capture("question"), capture("knowledge","with_proof"), capture("knowledge","without_proof")]
    assert len(bundle.COMMON) == 10
    assert "含证明专项" not in before[0]["system"]
    assert "无证明专项" not in before[1]["system"]
    assert "含证明专项" not in before[2]["system"]
    assert "恢复完整原题" not in before[1]["system"]
    assert "不得另行生成、搜索其他题" in before[1]["system"]
    original = bundle.entry
    monkeypatch.setattr(bundle, "entry", lambda name: original(name) + ("\n局部调整" if name == "knowledge/with_proof.md" else ""))
    after = [capture("question"), capture("knowledge","with_proof"), capture("knowledge","without_proof")]
    assert before[0] == after[0]
    assert before[2] == after[2]
    assert before[1] != after[1]

def test_auto_is_mutually_exclusive():
    rules = capture("knowledge")
    assert "以下两种专项互斥" in rules["system"]
    assert all(not x["id"].startswith("A") for x in rules["examples"])
