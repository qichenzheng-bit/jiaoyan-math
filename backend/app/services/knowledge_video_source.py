"""Capture a knowledge unit and its explicit question-bank links, without changing bank data."""
import hashlib
import json
import re

from fastapi import HTTPException
from sqlalchemy import select

from app.core.method_recommendation import video_solution
from app.models import TeachingResource

SCHEMA = "knowledge-video-source-v1"
DETAIL_FIELDS = ("conditions", "applications", "methods", "mistakes")
# The final assembled prompt is also checked by the engine; never truncate source data.
MAX_SOURCE_BYTES = 60000
TRANSPORT_PREFIX = "JIAOYAN_KNOWLEDGE_V1\n"
NO_PROOF = {"", "略", "证明略", "证明从略", "推导略", "无", "暂无", "待补充", "见教材"}


def teaching_type(proof):
    cleaned = re.sub(r"[\s。．.!！?？:：；;（）()]+", "", proof or "")
    # Empty or placeholder proof does not exclude a proof embedded in the正文.
    # AI resolves auto within generation, without another model call.
    return "auto" if cleaned in NO_PROOF else "with_proof"


def question_snapshot(row):
    if row.archived or row.kind != "question":
        raise HTTPException(422, "关联题目不可用，请在知识库调整关联")
    facts = getattr(row, "bank_facts", None)
    if facts is not None and (not facts.get("answer_complete") or not facts.get("solution_complete")):
        raise HTTPException(422, "关联题目答案或解析不完整，请先在题库补齐")
    try:
        solution = video_solution(row)
    except ValueError as exc:
        raise HTTPException(422, "关联题目：" + str(exc)) from exc
    if not (row.content or "").strip() or not (solution or "").strip():
        raise HTTPException(422, "关联题目正文或解析不完整")
    return {"id": row.id, "revision": row.revision, "title": row.title,
            "content": row.content, "answer": row.answer or "", "solution": solution,
            "subject": row.subject or "", "difficulty": row.difficulty or "",
            "question_type": row.question_type or ""}


def build_snapshot(unit, detail, linked_rows):
    if unit.archived or unit.kind != "knowledge":
        raise HTTPException(404, "请选择有效知识单元")
    if not (unit.title or "").strip() or not (unit.content or "").strip():
        raise HTTPException(422, "知识单元名称及正文不能为空")
    ids = detail.get("example_ids") or []
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "知识单元关联题目重复，请先整理")
    by_id = {row.id: row for row in linked_rows}
    if any(ident not in by_id for ident in ids):
        raise HTTPException(422, "关联题目不可用，请恢复或解除关联，不能当作无关联")
    candidates = [question_snapshot(by_id[ident]) for ident in ids]
    proof = unit.proof or ""
    data = {"schema": SCHEMA, "business_type": "knowledge",
            "teaching_type": teaching_type(proof),
            "resource_id": unit.id, "resource_revision": unit.revision,
            "title": unit.title, "subject": unit.subject or "", "chapter": unit.chapter or "",
            "unit_type": unit.unit_type or "", "content": unit.content, "proof": proof,
            "knowledge_tags": unit.tags or [],
            "teaching_detail": {k: detail.get(k, "") for k in DETAIL_FIELDS},
            "related_questions": candidates, "association_count": len(ids), "fps": 60}
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_SOURCE_BYTES:
        raise HTTPException(422, "知识单元及关联题超过视频输入预算，请整理资料；系统不会截断或替换关联题")
    return {**data, "source_sha256": hashlib.sha256(raw).hexdigest()}


def capture(db, unit):
    from app.api.resources import unit_detail_state
    detail = unit_detail_state(db, unit.id)
    ids = detail.get("example_ids") or []
    rows = list(db.scalars(select(TeachingResource).where(
        TeachingResource.id.in_(ids), TeachingResource.kind == "question"
    ))) if ids else []
    return build_snapshot(unit, detail, rows)


def transport(data):
    """Legacy lesson storage envelope; never exposed as a reference solution to the teacher."""
    from app.services import video_figures
    normalized, ids = video_figures.prepare_knowledge(data)
    envelope = TRANSPORT_PREFIX + json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # Preserve exact source hash across generation, edit and old contract verification.
    result = {"title": data["title"], "problem": normalized["content"], "reference_solution": envelope,
              "answer": "", "analysis": "", "subject": data["subject"], "chapter": data["chapter"],
              "exam_type": "", "question_type": "", "tags": data["knowledge_tags"], "fps": 60}
    for key, size in {"title":180,"problem":20000,"reference_solution":120000,"subject":20,"chapter":120}.items():
        if len(result[key]) > size:
            raise HTTPException(422, "知识单元字段超过引擎限制：" + key)
    return result, ids
