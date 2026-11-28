"""场景代码修复 · 最多三轮

规则：
    第 1 轮正常生成；失败把**具体错误 + 相关代码**反馈给 AI；
    第 2、3 轮针对性修复；三轮仍失败就停下，保留诊断日志。

硬约束：
    - 只修代码，不改题目与答案；
    - 同一错误没有实质进展时不再空跑模型；
    - 每轮的真实耗时、字符数、token 与调用次数都记账。
"""
from __future__ import annotations

import time
from pathlib import Path

from .scene_codegen import (
    Attempt,
    GeneratedScenes,
    SceneCodeRejected,
    build_contract,
    extract_blocks,
    generate_scene_sources,
    system_prompt,
    usage_delta,
    usage_snapshot,
    write_scenes,
)
from .scene_model_call import invoke_scene_model
from .scene_repair_support import (
    MAX_ROUNDS, RepairReport, _current_sources, _failed_scenes,
    _merge, _repair_prompt, _signature, _write_report,
)
from .source_assets import LessonSource
from .prompt_bundle import repair_system


class SceneRepairFailed(RuntimeError):
    def __init__(self, message: str, diagnostics: dict):
        super().__init__(message)
        self.diagnostics = diagnostics


def _log_round_tokens(log, round_index: int, tokens: dict | None) -> None:
    if not log or not tokens:
        return
    inp = int(tokens.get("input") or tokens.get("input_tokens") or 0)
    out = int(tokens.get("output") or tokens.get("output_tokens") or 0)
    if inp > 0 or out > 0:
        prefix = "" if round_index == 1 else f"第 {round_index} 轮："
        log("Token", f"{prefix}输入 {inp:,} token，输出 {out:,} token，总共 {inp + out:,} token")


def generate_with_repair(*, source: LessonSource, client, output_dir: Path,
                         fps: int, log=None, phase=None,
                         images: tuple[str, ...] = (),
                         watermark_style: dict | None = None,
                         cache_dir: Path | None = None,
                         cancel_check=None) -> GeneratedScenes:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    report = RepairReport()
    previous: dict[str, str] = {}
    seen: set[str] = set()
    last_errors: list[str] = []
    last_validations = {}

    for round_index in range(1, MAX_ROUNDS + 1):
        if cancel_check is not None:
            cancel_check()
        if round_index == 1:
            if phase:
                phase("生成 Manim 代码")
            # 「开始生成」由 scene_codegen 记录一次，这里不再重复打同样的日志。
            before = usage_snapshot(client)
            started = time.monotonic()
            try:
                generated = generate_scene_sources(
                    source=source, client=client, output_dir=folder,
                    fps=fps, log=log, phase=phase, images=images,
                    watermark_style=watermark_style)
                generated.attempts[0].round = 1
                _log_round_tokens(log, 1, generated.attempts[0].tokens)
                report.add(generated.attempts[0])
                generated.attempts = [Attempt(**item) for item in report.rounds]
                generated.tokens = dict(report.tokens)
                if log:
                    log("校验", "校验完毕")
                _write_report(folder, report, ok=True)
                return generated
            except SceneCodeRejected as exc:
                seconds = time.monotonic() - started
                tokens = usage_delta(before, usage_snapshot(client))
                drafts = _current_sources(folder)
                draft_chars = sum(len(code) for code in drafts.values())
                report.add(Attempt(round=1, ok=False, seconds=seconds,
                                   chars=draft_chars, tokens=tokens, errors=exc.errors))
                last_errors = exc.errors
                last_validations = exc.validations
                previous = drafts
                if log:
                    first_line = str(exc.errors[0]).splitlines()[0]
                    log("校验", f"第 1 轮失败：{first_line[:120]}")
            signature = _signature(last_errors)
            if signature in seen:
                _write_report(folder, report, ok=False, errors=last_errors)
                raise SceneRepairFailed(
                    "SCENE_REPAIR_NO_PROGRESS: 错误与上一轮完全一致",
                    report.to_dict())
            seen.add(signature)
            continue

        if not previous:
            previous = _current_sources(folder)
        if phase:
            phase(f"修复代码（第 {round_index} 轮）")
        if log:
            log("修复", f"AI 正在修复代码（第 {round_index} 轮）")
        try:
            user = _repair_prompt(source, last_errors, previous, fps=fps,
                                  watermark_style=watermark_style)
            response = invoke_scene_model(
                client,
                system=repair_system(folder, user),
                user_json=user,
                timeout=1800, images=list(images) or None,
            )
        except Exception as exc:
            err_msg = f"SCENE_REPAIR_CALL_FAILED: {type(exc).__name__}: {exc}"
            _write_report(folder, report, ok=False, errors=[err_msg])
            raise SceneRepairFailed(err_msg, report.to_dict()) from exc
        text = response.text
        seconds = response.seconds
        tokens = response.tokens
        _log_round_tokens(log, round_index, tokens)

        blocks = extract_blocks(text)
        merged = _merge(previous, blocks)
        if not merged:
            report.add(Attempt(round=round_index, ok=False, seconds=seconds,
                               chars=len(text), tokens=tokens,
                               errors=["SCENE_REPAIR_NO_CODE"]))
            last_errors = ["SCENE_REPAIR_NO_CODE: 模型没有返回代码块"]
            continue

        try:
            generated = write_scenes(
                merged, folder / "scenes", question=source.problem,
                reference_solution=source.reference_solution)
        except SceneCodeRejected as exc:
            report.add(Attempt(round=round_index, ok=False, seconds=seconds,
                               chars=len(text), tokens=tokens, errors=exc.errors))
            last_errors = exc.errors
            last_validations = exc.validations
            previous = _current_sources(folder) or previous
            if log:
                first_line = str(exc.errors[0]).splitlines()[0]
                log("校验", f"第 {round_index} 轮失败：{first_line[:120]}")
            signature = _signature(last_errors)
            if signature in seen:
                _write_report(folder, report, ok=False, errors=last_errors)
                raise SceneRepairFailed(
                    "SCENE_REPAIR_NO_PROGRESS: 错误与上一轮完全一致",
                    report.to_dict())
            seen.add(signature)
            continue

        report.add(Attempt(round=round_index, ok=True, seconds=seconds,
                           chars=len(text), tokens=tokens))
        # 每一轮的真实记录都要带出去：轮数、耗时、字数、token。
        generated.attempts = [Attempt(**item) for item in report.rounds]
        generated.tokens = dict(report.tokens)
        if log:
            log("校验", "校验完毕")
        _write_report(folder, report, ok=True)
        return generated

    _write_report(folder, report, ok=False, errors=last_errors)
    raise SceneRepairFailed(
        f"SCENE_REPAIR_EXHAUSTED: {MAX_ROUNDS} 轮仍未通过；最后错误："
        + (last_errors[0][:200] if last_errors else "unknown"),
        report.to_dict())


def contract_of(generated: GeneratedScenes, *, source: LessonSource,
                fps: int) -> "object":
    return build_contract(
        generated, question=source.problem, fps=fps,
        extra_meta={
            "question_sha256": source.question_sha256,
            "source_sha256": source.source_sha256,
            "generation": generated.tokens,
        })


__all__ = [
    "MAX_ROUNDS", "SceneRepairFailed", "RepairReport",
    "generate_with_repair", "contract_of",
]
