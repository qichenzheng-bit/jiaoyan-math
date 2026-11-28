import importlib.util
import json
import sys
from pathlib import Path

import pytest
from app.services import knowledge_video_source as local
from app.services import video_figures
from test_knowledge_video_source import unit, question

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("knowledge_source_assets", ROOT / "vendor/video-overlay/app/backend/src/weiguang_backend/pipeline/source_assets.py")
assets = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = assets
spec.loader.exec_module(assets)


def test_knowledge_payload_is_not_a_question_solution():
    data = local.build_snapshot(unit(), {"example_ids": ["a"]}, [question("a")])
    legacy, figures = local.transport(data)
    assert not figures
    source = assets.prepare_lesson_source(legacy["problem"], legacy["reference_solution"], legacy["answer"])
    payload = json.loads(source.prompt_payload(fps=60))
    assert payload["business_type"] == "knowledge"
    assert payload["knowledge_unit"]["related_questions"][0]["id"] == "a"
    assert "problem" not in payload and "reference_solution" not in payload
    assert source.question_meta["source_context"]["business_type"] == "knowledge"
    assert source.source_sha256 == assets.prepare_lesson_source(legacy["problem"], legacy["reference_solution"]).source_sha256


def test_empty_proof_remains_empty():
    data = local.build_snapshot(unit(), {"example_ids": []}, [])
    legacy, _ = local.transport(data)
    source = assets.prepare_lesson_source(legacy["problem"], legacy["reference_solution"])
    assert json.loads(source.prompt_payload(fps=60))["knowledge_unit"]["proof"] == ""


def test_malformed_envelope_is_rejected():
    with pytest.raises(assets.SourceInputError):
        assets.prepare_lesson_source("定义", assets.KNOWLEDGE_PREFIX + "{}")
