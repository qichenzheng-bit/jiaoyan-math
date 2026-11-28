from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from app.services import knowledge_video_source as source


def unit(**overrides):
    return SimpleNamespace(**{"id": "u", "revision": 2, "kind": "knowledge", "archived": False,
        "title": "极限", "content": "定义", "proof": "", "subject": "数学分析",
        "chapter": "", "unit_type": "定义", "tags": ["极限"], **overrides})


def question(ident, **overrides):
    return SimpleNamespace(**{"id": ident, "revision": 1, "kind": "question", "archived": False,
        "title": "例题", "content": "计算极限", "answer": "0", "solution": "直接代入",
        "subject": "数学分析", "difficulty": "简单", "question_type": "计算题", **overrides})


def test_no_link_does_not_import_other_questions():
    data = source.build_snapshot(unit(), {"example_ids": []}, [question("unlinked")])
    assert data["related_questions"] == []
    assert data["association_count"] == 0
    assert data["teaching_type"] == "auto"


def test_exact_links_in_order_and_revision():
    data = source.build_snapshot(unit(proof="由定义证明"), {"example_ids": ["b", "a"]},
                                 [question("a"), question("b"), question("unlinked")])
    assert [q["id"] for q in data["related_questions"]] == ["b", "a"]
    assert data["teaching_type"] == "with_proof"
    changed = source.build_snapshot(unit(proof="由定义证明"), {"example_ids": ["b", "a"]},
                                    [question("a", revision=2), question("b")])
    assert data["source_sha256"] != changed["source_sha256"]


@pytest.mark.parametrize("rows", [[], [question("a", archived=True)], [question("a", solution="")]])
def test_invalid_link_is_not_no_link(rows):
    with pytest.raises(HTTPException):
        source.build_snapshot(unit(), {"example_ids": ["a"]}, rows)


def test_no_silent_truncation():
    with pytest.raises(HTTPException):
        source.build_snapshot(unit(content="数学" * 30000), {"example_ids": []}, [])
