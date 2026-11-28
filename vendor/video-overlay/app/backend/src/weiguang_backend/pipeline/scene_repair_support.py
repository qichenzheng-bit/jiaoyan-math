"""Manim 代码修复辅助：轮次报告、错误归并、修复提示与草稿恢复。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .scene_output import Attempt
from .source_assets import LessonSource
from animation_engine.render.layout_constraints import layout_prompt_fields

MAX_ROUNDS = 3


@dataclass
class RepairReport:
    rounds: list[dict] = field(default_factory=list)
    tokens: dict = field(default_factory=lambda: {
        "input": 0, "output": 0, "cached": 0, "calls": 0})
    total_seconds: float = 0.0

    def add(self, attempt: Attempt) -> None:
        self.rounds.append(attempt.to_dict())
        for key in ("input", "output", "cached", "calls"):
            self.tokens[key] += int(attempt.tokens.get(key) or 0)
        self.total_seconds += attempt.seconds

    def to_dict(self) -> dict:
        return {
            "rounds": self.rounds,
            "tokens": self.tokens,
            "total_seconds": round(self.total_seconds, 2),
        }

def _signature(errors: list[str]) -> str:
    """错误签名：错误码 + 定位 + 细节。

    细节必须参与比较。曾经的实现只看「码 + 行号」，于是第 2 轮把 `\\lor` 换成
    另一个非法符号时（位置与错误码都没变、具体原因已经变了）会被判成「错误与
    上一轮完全一致」，直接放弃、白扔第 3 轮修复机会。细节按空白归一后截断，
    避免换行/空格差异把同一条错误看成两条。
    """
    parts = []
    for item in errors:
        head, _, detail = item.partition(":")
        line = ""
        for token in head.split():
            if token.isdigit() and len(token) <= 5:
                line = token
                break
        parts.append(f"{head.strip()}:{line}:" + " ".join(detail.split())[:60])
    return "|".join(sorted(parts))


def _failed_scenes(errors: list[str], previous: dict[str, str]) -> dict[str, str]:
    """只把出错场景回传：整节课代码全塞回去会白白拉长输入。"""
    names: set[str] = set()
    for item in errors:
        for match in re.finditer(r"\[([A-Za-z0-9_\-]+)\]", item):
            if match.group(1) in previous:
                names.add(match.group(1))
    if not names:
        return dict(previous)
    return {name: previous[name] for name in sorted(names)}


def _repair_prompt(source: LessonSource, errors: list[str],
                   previous: dict[str, str], *, fps: int,
                   watermark_style: dict | None = None,
                   repair_loci: list[dict] | None = None) -> str:
    targets = _failed_scenes(errors, previous)
    blocks = "\n\n".join(
        f"```python title={name}\n{code.rstrip()}\n```"
        for name, code in sorted(targets.items())
    )
    payload = {
        **json.loads(source.prompt_payload(fps=fps)),
        **layout_prompt_fields(watermark_style),
        "validation_errors": errors[:8],
        "current_code": blocks,
        "instruction": (
            "只修复上面列出的错误，不要改动题目、答案解析或核心教学结构。"
            "禁止为了让检查通过而删掉讲解步骤，保留第一幕自然开场白与有效推导。"
            "修复后的代码块必须沿用原场景标题（如 ```python title=scene_01），"
            "不要自造新标题，也不要把同一个 cue_id 写进多个场景。"
            "若 MathTex/Tex 多行拼接，请确认 \\qquad、\\quad、\\displaystyle 等无参命令"
            "结尾引号前留有空格，避免与下一行字母黏连成未定义宏。"
        ),
    }
    if payload.get("business_type") == "knowledge":
        payload["instruction"] += " 知识单元的正文、证明、关联题及教学类型元数据均保持原样；仅修复真实技术错误。"
    if repair_loci:
        payload["repair_loci"] = repair_loci
    return json.dumps(payload, ensure_ascii=False, indent=2)


_CLASS_NAME_RE = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
_CUE_ID_RE = re.compile(r"""self\.start_cue\s*\(\s*["']([^"']+)["']""")


def _matching_previous_key(code: str, merged: dict[str, str],
                           replaced: set[str]) -> str | None:
    """将 AI 改名后的修复块匹配回对应的原场景名，避免产生重复场景。"""
    candidates = [key for key in merged if key not in replaced]
    if not candidates:
        return None
    classes = set(_CLASS_NAME_RE.findall(code))
    cues = set(_CUE_ID_RE.findall(code))
    matched = [
        key for key in candidates
        if (classes and classes & set(_CLASS_NAME_RE.findall(merged[key])))
        or (cues and cues & set(_CUE_ID_RE.findall(merged[key])))
    ]
    if len(matched) == 1:
        return matched[0]
    return None


def _merge(previous: dict[str, str], blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """未返回的场景沿用上一轮代码，避免修复时丢场景，同时防止改名产生重复场景。"""
    if not blocks:
        return [(name, code) for name, code in previous.items()]
    if len(previous) == 1 and len(blocks) == 1:
        return [(next(iter(previous)), blocks[0][1])]
    merged = dict(previous)
    ordered = sorted(previous)
    replaced: set[str] = set()
    untitled = [code for name, code in blocks if not name]
    for index, code in enumerate(untitled):
        name = ordered[index] if index < len(ordered) else f"scene_{index + 1:02d}"
        merged[name] = code
        replaced.add(name)
    for name, code in blocks:
        if not name:
            continue
        if name in merged:
            merged[name] = code
            replaced.add(name)
            continue
        target = _matching_previous_key(code, merged, replaced)
        if target is None:
            unreplaced = [k for k in ordered if k not in replaced]
            target = unreplaced[0] if len(unreplaced) == 1 else name
        merged[target] = code
        replaced.add(target)
    return list(merged.items())

def _current_sources(folder: Path) -> dict[str, str]:
    """优先取已通过校验的场景；校验没过时取草稿，保证修复轮次看得到原代码。"""
    for name in ("scenes", "draft"):
        directory = folder / name
        if not directory.is_dir():
            continue
        sources = {path.stem: path.read_text(encoding="utf-8")
                   for path in sorted(directory.glob("*.py"))}
        if sources:
            return sources
    return {}


def _write_report(folder: Path, report: RepairReport, *, ok: bool,
                  errors: list[str] | None = None) -> None:
    payload = report.to_dict()
    payload["ok"] = ok
    payload["max_rounds"] = MAX_ROUNDS
    if errors:
        payload["final_errors"] = errors[:12]
    (folder / "generation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

