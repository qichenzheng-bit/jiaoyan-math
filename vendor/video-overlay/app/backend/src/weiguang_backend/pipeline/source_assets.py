"""输入预处理 · 题目、解析与答案

职责：
    把用户输入整理成生成提示词可以直接使用的形状，并锁定来源指纹。

不做：
    不判数学对错，不做难度分类，不拆解题步骤。用户输入即可信来源。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

SOURCE_SCHEMA = "v6-source-1"
KNOWLEDGE_PREFIX = "JIAOYAN_KNOWLEDGE_V1\n"
KNOWLEDGE_SCHEMA = "knowledge-video-source-v1"

def knowledge_envelope(value):
    if not isinstance(value, str) or not value.startswith(KNOWLEDGE_PREFIX):
        return None
    try:
        data = json.loads(value[len(KNOWLEDGE_PREFIX):])
    except (ValueError, TypeError) as exc:
        raise SourceInputError("KNOWLEDGE_SOURCE_INVALID") from exc
    if (not isinstance(data, dict) or data.get("schema") != KNOWLEDGE_SCHEMA
        or data.get("business_type") != "knowledge"
        or data.get("teaching_type") not in {"with_proof","without_proof","auto"}
        or not isinstance(data.get("content"), str) or not data["content"].strip()
        or not isinstance(data.get("related_questions"), list)
        or data.get("association_count") != len(data["related_questions"])):
        raise SourceInputError("KNOWLEDGE_SOURCE_INVALID")
    return data
MAX_PROBLEM = 20_000
MAX_SOLUTION = 120_000
MAX_ANSWER = 4_000

PLACEHOLDER_SOLUTIONS = frozenset({
    "待补充", "待补充解析", "待完善", "待完善解析",
    "暂无", "暂无解析", "略", "见答案", "待定", "tbd", "todo",
})


def is_placeholder_solution(text: str, answer: str = "") -> bool:
    """判断解析是否为占位文本或仅抄了简短最终答案，禁止未经正式解析就送入视频生产。"""
    cleaned = strip_page_furniture(text).strip()
    if not cleaned:
        return True
    token = re.sub(r"[\s。．.!！?？:：;；,，、()（）\[\]【】]+", "", cleaned).lower()
    if token in PLACEHOLDER_SOLUTIONS:
        return True
    ans = strip_page_furniture(answer).strip()
    if ans and cleaned == ans and len(cleaned) <= 8:
        return True
    return False


def validate_solution_ready_for_video(reference_solution: str, answer: str = "") -> None:
    """仅做资料完整性守门（禁止空文本与占位解析进入视频生产），不审查数学正确性。"""
    cleaned = strip_page_furniture(reference_solution).strip()
    if not cleaned:
        raise SourceInputError("SOURCE_SOLUTION_EMPTY")
    if is_placeholder_solution(cleaned, answer=answer):
        raise SourceInputError("SOURCE_SOLUTION_PLACEHOLDER")


def merge_choice_options(stem: str, options) -> str:
    """把独立 options 字段按统一格式合并进题干正文（避免重复追加已内嵌的选项）。"""
    base = strip_page_furniture(stem)
    if not options or not isinstance(options, (list, tuple)):
        return base
    if re.search(r"(?:^|\n|\s)[\(（]?A[\)）\.．、]", base):
        return base
    lines: list[str] = []
    for idx, opt in enumerate(options):
        if isinstance(opt, dict):
            label = str(opt.get("label") or opt.get("key") or chr(65 + idx)).strip()
            body = str(opt.get("text") or opt.get("content") or opt.get("value") or "").strip()
        else:
            label = chr(65 + idx)
            body = str(opt or "").strip()
        if not body:
            continue
        lines.append(f"{label}．{body}")
    if not lines:
        return base
    return (base + ("\n\n" if base else "") + "\n".join(lines)).strip()


class SourceInputError(ValueError):
    """输入不完整或不可用；消息前缀即错误码。"""


@dataclass(frozen=True)
class LessonSource:
    problem: str
    reference_solution: str
    answer: str
    question_sha256: str
    source_sha256: str
    anchors: tuple[str, ...]
    # 只用于生成提示词，不参与来源指纹（改标签不该让已生成的场景失效）
    question_meta: dict = field(default_factory=dict)
    opening_line: str = ""

    def prompt_payload(self, *, fps: int) -> str:
        unit = knowledge_envelope(self.reference_solution)
        if unit is not None:
            return json.dumps({"business_type":"knowledge", "knowledge_unit":unit, "fps":fps,
                               "question_meta":self.question_meta}, ensure_ascii=False, indent=2)
        return json.dumps({
            "problem": self.problem,
            "reference_solution": self.reference_solution,
            "answer": self.answer,
            "fps": fps,
            "question_meta": self.question_meta,
            "opening_line": self.opening_line,
        }, ensure_ascii=False, indent=2)


# 仅做输入数据标签清洗，不在Python预设任何教学开场与场景。
_SPLIT_RE = re.compile(r"[、,，;；/|\s]+")
_PUNCT = "。．.!！?？:：~～ "


def _clean_text(value) -> str:
    return str(value or "").strip().strip(_PUNCT)


def _list_values(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw = [str(item).strip() for item in value]
    else:
        text = str(value or "").strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                raw = ([str(item).strip() for item in parsed]
                       if isinstance(parsed, list) else [])
            except (TypeError, ValueError):
                raw = []
        else:
            raw = _SPLIT_RE.split(text)
    out: list[str] = []
    for item in raw:
        item = _clean_text(item)
        if item and item not in out:
            out.append(item)
    return out[:8]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# 扫描试卷带入的页眉页脚：与题目本身无关，必须在入库/生成/渲染前清掉。
_PAGE_NOTES = re.compile(
    r"(?:[（(\[【]\s*(?:"
    r"(?:本体|本题)?题干\s*(?:续下页|接下页|转下页|接上页|承上页|续上页)"
    r"|续下页|接下页|接上页|续上页|转下页|承上页|续前页|下页续|本页完|下页见"
    r"|(?:上接|下转)\s*第\s*\d+\s*页"
    r"|第\s*\d+\s*页\s*[，,/／]?\s*共\s*\d+\s*页"
    r")\s*[)）\]】]"
    r"|(?:本体|本题)题干\s*(?:续下页|接下页|转下页|接上页|承上页|续上页)"
    r"|(?:^|(?<=\s))(?:续下页|接下页|接上页|续上页|转下页|承上页)(?=\s|$))"
)
def strip_page_furniture(text) -> str:
    """只清「（接上页）」「（本题题干续下页）」这类页脚。

    题面里的填空横线（`____`、`＿＿`）是题目内容的一部分，必须原样保留；
    朗读时由提示词约束「不念下划线」，不能在这里删掉。
    """
    if not text:
        return ""
    cleaned = _PAGE_NOTES.sub("", str(text))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def source_anchors(text: str) -> tuple[str, ...]:
    """题干里必须被讲到的硬条件：数字与短公式片段。"""
    # 不带负号：口播里说「减 4」不会出现 "-4"，带符号会让条件覆盖被误判成遗漏。
    anchors = re.findall(r"\d+(?:\.\d+)?", text)
    anchors += re.findall(r"\\?[a-zA-Z]\s*\^\s*\{?\d", text)
    unique: list[str] = []
    for item in anchors:
        if item not in unique:
            unique.append(item)
    return tuple(unique)


SOURCE_CONTEXT_PROVIDER = lambda: {}


def lesson_question_meta(lesson) -> dict:
    """从题目记录提取生成与修复共用的非指纹元信息。"""
    return {
        "exam_type": getattr(lesson, "exam_type", "") or "",
        "subject": getattr(lesson, "subject", "") or "",
        "chapter": getattr(lesson, "chapter", "") or "",
        "question_type": getattr(lesson, "question_type", "") or "",
        "tags": getattr(lesson, "tags", "") or "",
        "title": getattr(lesson, "title", "") or "",
        "source_context": SOURCE_CONTEXT_PROVIDER(),
    }


def prepare_lesson_source(problem: str, reference_solution: str,
                          answer: str = "", *, meta: dict | None = None) -> LessonSource:
    # 题干里夹带的「（接上页）」类页脚先清掉：它们不是题目内容，
    # 一旦进提示词就会出现在视频口播与板书里。
    unit = knowledge_envelope(reference_solution)
    problem = strip_page_furniture(problem)
    if unit is None:
        reference_solution = strip_page_furniture(reference_solution)
    else:
        # Envelope is immutable, so all generation/render/edit guards compute the same hash.
        if problem != strip_page_furniture(unit["content"]):
            raise SourceInputError("KNOWLEDGE_SOURCE_MISMATCH")
    # 存量题目没有答案，允许为空；有新录入时才作为可信结论进入提示词。
    answer = strip_page_furniture(answer)
    if not problem:
        raise SourceInputError("SOURCE_PROBLEM_EMPTY")
    if not reference_solution:
        raise SourceInputError("SOURCE_SOLUTION_EMPTY")
    if len(problem) > MAX_PROBLEM:
        raise SourceInputError(f"SOURCE_PROBLEM_TOO_LONG: {len(problem)} > {MAX_PROBLEM}")
    if len(reference_solution) > MAX_SOLUTION:
        raise SourceInputError(f"SOURCE_SOLUTION_TOO_LONG: {len(reference_solution)} > {MAX_SOLUTION}")
    if len(answer) > MAX_ANSWER:
        raise SourceInputError(f"SOURCE_ANSWER_TOO_LONG: {len(answer)} > {MAX_ANSWER}")
    meta = meta or {}
    question_meta = {
        "exam_type": _clean_text(meta.get("exam_type")),
        "subject": _clean_text(meta.get("subject")),
        "chapter": _clean_text(meta.get("chapter")),
        "question_type": _clean_text(meta.get("question_type")),
        "tags": _list_values(meta.get("tags")),
        "title": _clean_text(meta.get("title")),
    }
    context = meta.get("source_context")
    if isinstance(context, dict) and context:
        question_meta["source_context"] = context
    if unit is not None:
        question_meta["source_context"] = {**question_meta.get("source_context", {}),
            "business_type":"knowledge", "teaching_type":unit["teaching_type"]}
    raw_alts = meta.get("alternative_methods")
    if isinstance(raw_alts, list) and raw_alts:
        alts = [
            {
                "label": _clean_text(item.get("label")),
                "preview": str(item.get("preview") or "").strip()[:180],
            }
            for item in raw_alts[:3]
            if isinstance(item, dict) and str(item.get("preview") or "").strip()
        ]
        if alts:
            question_meta["alternative_methods"] = alts
    return LessonSource(
        problem=problem,
        reference_solution=reference_solution,
        answer=answer,
        question_sha256=_digest(problem),
        source_sha256=_digest(f"{SOURCE_SCHEMA}\n{problem}\n{reference_solution}\n{answer}"),
        anchors=source_anchors(problem),
        question_meta=question_meta,
        # 教学开场由 AI 根据统一教师提示词编写，而非 Python 生成固定话术。
        opening_line="",
    )


_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_MD_IMAGE_SIZE_RE = re.compile(r"^\d+(?:\.\d+)?(?:%|px)$")


def parse_work_image_url(url: str) -> str:
    """Extract the stored path `p` from a local work-image download URL."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if not parsed.path.endswith("/chat/files/download"):
        return ""
    qs = parse_qs(parsed.query)
    values = qs.get("p") or []
    return unquote(str(values[0])).strip() if values and values[0] else ""


def parse_markdown_image_alt(alt: str) -> tuple[str, str, str]:
    """Parse `caption|width|align` encoded in Markdown image alt text."""
    parts = str(alt or "").split("|")
    caption = parts[0].strip() if parts else ""
    width = parts[1].strip() if len(parts) > 1 and _MD_IMAGE_SIZE_RE.match(parts[1].strip()) else ""
    align = parts[2].strip() if len(parts) > 2 and parts[2].strip() in ("center", "right") else ""
    return caption, width, align


def replace_markdown_images_for_prompt(text: str) -> str:
    """Replace work-image download URLs with readable placeholders for LLM prompts."""
    src = str(text or "")
    if "![" not in src:
        return src

    def _sub(m: re.Match) -> str:
        path = parse_work_image_url(m.group(2))
        if not path:
            return m.group(0)
        caption, _, _ = parse_markdown_image_alt(m.group(1))
        return f"[参考附图：{caption}]" if caption else "[参考附图]"

    return _MD_IMAGE_RE.sub(_sub, src)


def sync_markdown_image_refs(existing_raw: str, fields: dict[str, str]) -> str:
    """Merge Markdown work images from lesson text fields into `Lesson.image_refs` JSON."""
    try:
        parsed = json.loads(existing_raw or "[]")
    except (TypeError, ValueError):
        parsed = []
    items = [dict(x) for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else []

    field_map = {
        "problem": "problem",
        "answer": "answer",
        "analysis": "analysis",
        "reference_solution": "solution",
        "solution": "solution",
    }
    touched_fields = {field_map[k] for k in fields if k in field_map}
    # Preserve non-upload (e.g., AI-ingested/drawn) entries and upload entries for untouched fields.
    kept: list[dict] = []
    existing_keys: set[tuple[str, str]] = set()
    for item in items:
        f = str(item.get("field") or "problem").strip().lower()
        kind = str(item.get("kind") or "").strip().lower()
        p = str(item.get("path") or "").strip()
        if kind == "upload" and f in touched_fields:
            continue
        kept.append(item)
        if p:
            existing_keys.add((f, str(Path(p)) if p else p))

    for src_key, text in fields.items():
        target_field = field_map.get(src_key)
        if not target_field or not text:
            continue
        for m in _MD_IMAGE_RE.finditer(str(text)):
            img_path = parse_work_image_url(m.group(2))
            if not img_path:
                continue
            caption, width, align = parse_markdown_image_alt(m.group(1))
            norm_path = str(Path(img_path))
            key = (target_field, norm_path)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            entry = {
                "field": target_field,
                "path": img_path,
                "caption": caption,
                "kind": "upload",
            }
            if width:
                entry["width"] = width
            if align:
                entry["align"] = align
            kept.append(entry)

    return json.dumps(kept, ensure_ascii=False) if kept else ""


__all__ = [
    "SOURCE_SCHEMA",
    "SourceInputError",
    "LessonSource",
    "lesson_question_meta",
    "parse_markdown_image_alt",
    "parse_work_image_url",
    "prepare_lesson_source",
    "knowledge_envelope",
    "replace_markdown_images_for_prompt",
    "source_anchors",
    "strip_page_furniture",
    "sync_markdown_image_refs",
]
