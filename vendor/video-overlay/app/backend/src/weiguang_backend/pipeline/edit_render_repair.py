"""教学微调成片的真实 Manim 渲染错误修复。

仅编辑本轮被授权修改的文件；每轮以原始微调指令为最终核验依据。
不会对数学正确性作评价，也不会在失败时触碰已发布的版本。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from animation_engine.code.scene_contract import SceneContract
from animation_engine.code.scene_validator import validate_contract
from animation_engine.errors import EngineError

from .edit_executor import (
    EditOutputError, edit_payload, editor_system_prompt, merge_targeted_sources,
    validate_edit_scope_ast,
)
from .runtime_render_repair import repairable_render_error
from .scene_codegen import build_contract
from .scene_model_call import invoke_scene_model
from .scene_output import SceneCodeRejected, read_scene_sources, write_scenes

MAX_EDIT_RENDER_REPAIRS = 3


def recover_edited_render(
    *,
    attempt: Path,
    source_before: dict[str, str],
    tasks: tuple[str, ...],
    instruction: str,
    editable_files: tuple[str, ...],
    client,
    fps: int,
    render: Callable[[Path], dict],
    original_error: EngineError,
    reference_solution: str = "",
    question: str = "",
    answer: str = "",
    previous_question: str = "",
    source_modified: bool = False,
    watermark_style: dict | None = None,
    voice_rules: dict | None = None,
    images: list[str] | None = None,
    voice_only: bool = False,
    log=None,
    cancel_check=None,
) -> tuple[Path, dict]:
    """返回实际渲染成功的候选目录和报告；不修改原候选及历史成片。"""
    attempt = Path(attempt)
    base_contract = SceneContract.read(attempt / "scene_contract.json")
    active = read_scene_sources(attempt, base_contract)
    selected = tuple(name for name in editable_files if name in active)
    if not selected or not repairable_render_error(original_error):
        raise original_error
    effective_question = question or base_contract.question
    original_tasks = tuple(tasks)
    error = str(original_error)
    seen: set[tuple] = set()
    for round_index in range(1, MAX_EDIT_RENDER_REPAIRS + 1):
        if cancel_check:
            cancel_check()
        signature = (error[:1600], tuple(active.items()))
        if signature in seen:
            break
        seen.add(signature)
        if log:
            log("微调修复", f"运行失败，AI 针对原指令修复代码：{round_index}/{MAX_EDIT_RENDER_REPAIRS}")
        # 保留原指令及对应场景授权范围；防止技术修复重写无关教学流程。
        diagnostic = (
            "Manim 实际渲染技术错误（只允许修复当前授权文件中的引发报错位置）：\n"
            + error[:8000]
        )
        payload = edit_payload(
            original_tasks, base_contract, active, selected,
            reference_solution=reference_solution, answer=answer,
            previous_question=previous_question, source_modified=source_modified,
            errors=diagnostic,
            reference_images=tuple(images or ()),
            watermark_style=watermark_style, voice_rules=voice_rules,
            instruction=instruction, voice_only=voice_only,
        )
        response = invoke_scene_model(
            client, system=editor_system_prompt(), user_json=payload,
            timeout=1800, images=images or None,
        )
        try:
            candidate, modified = merge_targeted_sources(
                active, response.text, selected)
            if not modified:
                raise EditOutputError("EDIT_RENDER_REPAIR_NO_CODE_CHANGE")
            if tuple(candidate) != tuple(active):
                # 运行故障修复不得绕过最初微调的结构授权。
                raise EditOutputError("EDIT_RENDER_REPAIR_SCENE_SET_OR_ORDER_CHANGED")
            folder = attempt / "runtime_repair" / f"round_{round_index}"
            if voice_only:
                from .edit_executor import assert_only_tts_text_changed
                try:
                    assert_only_tts_text_changed(source_before, candidate)
                except EditOutputError as exc:
                    raise EditOutputError(
                        "EDIT_VOICE_ONLY_REPAIR_BLOCKED: 纯读音微调运行修复禁止修改板书/字幕，"
                        "请仅调整对应 cue 的 tts_text 或终止修改"
                    ) from exc
            generated = write_scenes(
                list(candidate.items()), folder / "scenes",
                question=effective_question,
                reference_solution=reference_solution,
            )
            contract = build_contract(
                generated, question=effective_question, fps=fps,
                extra_meta=dict(base_contract.meta),
            )
            problems = validate_contract(contract)
            if problems:
                raise EditOutputError("; ".join(map(str, problems)))
            if not voice_only:
                validate_edit_scope_ast(active, candidate, targets=selected)
            contract.write(folder / "scene_contract.json")
            try:
                report = render(folder)
                return folder, report
            except EngineError as exc:
                if not repairable_render_error(exc):
                    raise
                error = str(exc)
                for trace in sorted((folder / "work").glob("*.error.log")):
                    error += "\n" + trace.read_text(encoding="utf-8")[-9000:]
                active = candidate
        except (SceneCodeRejected, EditOutputError, ValueError) as exc:
            error = str(exc)[:9000]
    raise EditOutputError("EDIT_RENDER_REPAIR_EXHAUSTED: " + error[:800])


__all__ = ["recover_edited_render", "MAX_EDIT_RENDER_REPAIRS"]
