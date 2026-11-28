"""Dependency-free static tests for the staged video prompt overlay."""
import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "vendor/video-overlay/app/backend/src/weiguang_backend"
SPEC = importlib.util.spec_from_file_location("video_prompt_bundle", OVERLAY / "pipeline/prompt_bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)

def test_overlay_python_syntax():
    for path in OVERLAY.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

def test_fixed_rules_and_example_index():
    assert len(bundle.SHARED) == 13
    assert len(set(bundle.SHARED)) == 13
    shared = bundle.shared_specs()
    assert "静态校验" in shared and "防重叠" in shared
    entries = json.loads((bundle.PROMPTS_DIR / "examples/index.json").read_text())
    assert len({rec["id"] for rec in entries}) == len(entries)
    for rec in entries:
        assert (bundle.PROMPTS_DIR / "examples" / rec["path"]).is_file()

def test_deterministic_example_selection_and_snapshot(tmp_path):
    src = SimpleNamespace(question_meta={"tags":["极限","泰勒公式"]},problem="求极限",reference_solution="泰勒展开",source_sha256="a"*64)
    directory = tmp_path / "candidate"
    system = bundle.snapshot(src, "题源", directory)
    snap = json.loads((directory / "prompt_snapshot.json").read_text())
    assert snap["system"] == system
    assert snap["user_json"] == "题源"
    assert "A01" in {x["id"] for x in snap["examples"]}
    assert "A04" not in {x["id"] for x in snap["examples"]}
    assert bundle.repair_system(directory, "实际错误") == snap["repair_system"]
    assert bundle.snapshot(src, "题源", directory) == system

def test_no_match_and_budget():
    fixed = bundle.shared_specs()
    assert bundle.choose_examples({}, "", "", fixed, "题源") == (fixed, [])
    with pytest.raises(RuntimeError, match="VIDEO_PROMPT_BUDGET_EXCEEDED"):
        bundle.ensure_budget(fixed, "题"*50000)


def test_new_complete_example_drafts_are_python_syntax():
    entries = json.loads((bundle.PROMPTS_DIR / "examples/index.json").read_text())
    assert len(entries) == 42
    assert len([r for r in entries if r["kind"] == "complete"]) == 10
    for item in entries:
        if item["status"] != "new_complete_draft_unverified":
            continue
        body = (bundle.PROMPTS_DIR / "examples" / item["path"]).read_text()
        code = body.split("```python title=scene_01\n", 1)[1].split("```", 1)[0]
        ast.parse(code)


def test_opening_does_not_depend_on_exam_provenance():
    text = (bundle.PROMPTS_DIR / "shared/02_opening_reading.md").read_text()
    assert "不得依赖或主动播报试卷来源" in text
    assert "不强制开场白" in text
    example = (bundle.PROMPTS_DIR / "examples/teaching/B01_opening.md").read_text()
    assert "郑州大学" not in example
