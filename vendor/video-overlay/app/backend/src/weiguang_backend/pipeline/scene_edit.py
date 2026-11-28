"""V5 增量微调：智能分流 → 定位场景 → 最小代码修改 → 校验 → 缓存渲染。

所有候选视频先放 attempts；run_scene_edit 不修改 state/latest 或数据库。
由任务层核对修订号后，将候选升级为不可变版本，再发布数据库指针。
"""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from pathlib import Path

from animation_engine.code.scene_contract import SceneContract
from animation_engine.errors import EngineError
from animation_engine.code.scene_validator import (
    validate_contract, validate_lesson_sources, validate_scene_source,
)
from animation_engine.render.code_scene_render import render_code_lesson
from animation_engine.speech.subtitle_style import (
    apply_subtitle_instructions, normalize_subtitle_style,
)

from .edit_executor import (
    EditOutputError, assert_only_tts_text_changed, edit_payload,
    editor_system_prompt, manifest_layout_warnings, merge_targeted_sources,
    validate_edit_scope_ast,
)
from .edit_locator import EditTargets, locate_scenes
from .edit_render_repair import recover_edited_render
from .edit_structure import order_edited_scenes
from .edit_session_store import (
    STATE_SCHEMA, EditError, _current_version,
    _previous_audio, _read_state,
    complete_session_publish, create_session, export_history, latest_paths,
    record_feedback, shared_render_cache, synchronize_session_revision,
    update_state_source,
)
from .edit_router import (
    _is_explicit_source_regen, resolve_speech_rate, route_instruction_semantic,
)
from .runtime_render_repair import repair_rendered_lesson, repairable_render_error
from .scene_model_call import invoke_scene_model
from .scene_codegen import build_contract, usage_delta, usage_snapshot
from .scene_output import read_scene_sources
from .scene_repair import SceneRepairFailed, generate_with_repair
from .source_assets import LessonSource, prepare_lesson_source

MAX_EDIT_ROUNDS = 3


class EditNoChange(RuntimeError):
    """要求不在微调能力范围内，或算下来没有任何变化。

    这不是失败：按"不修改、不报错"处理，调用方应把任务记为成功且不动已发布的
    视频（旧视频继续可用）。
    """

    def __init__(self, reason: str = "") -> None:
        super().__init__(reason or "EDIT_NO_CHANGE")
        self.reason = reason






def _validate_sources(sources: dict[str, str], *, question: str,
                      reference_solution: str) -> list[str]:
    errors: list[str] = []
    results = {}
    for name, code in sources.items():
        result = validate_scene_source(
            code, question=question, reference_solution=reference_solution)
        results[name] = result
        if not result.ok:
            errors.append(f"[{name}] {result.error_text()}")
    if not errors:
        problems, _warnings = validate_lesson_sources(
            results, question=question, reference_solution=reference_solution)
        errors.extend("[lesson] " + str(problem) for problem in problems)
    return errors


class _AsGenerated:
    """兼容生成阶段 build_contract，不修改原始文件名及场景顺序。"""
    def __init__(self, pairs: dict[str, str]):
        self.sources = pairs
        self.files = {name: f"scenes/{name}.py" for name in pairs}
        self.validations = {}
        self.attempts = []
        self.tokens = {}


def _regenerate_from_latest_source(
    session: Path,
    *,
    attempt: Path,
    revision: int,
    instruction: str,
    effective_source: LessonSource,
    contract_source_sha256: str = "",
    client,
    fps: int,
    contract: SceneContract,
    source_images: tuple[str, ...],
    new_voice: str,
    new_rate: str,
    old_pitch: str,
    old_volume: str,
    style: dict,
    selected_voice_rules: dict | None,
    watermark_style: dict | None,
    intent,
    log=None,
    phase=None,
    cancel_check=None,
    progress=None,
) -> dict:
    """微调中明确要求「以最新题目重新生成视频」时，走整片生成与渲染流程。"""
    started = time.monotonic()
    before = usage_snapshot(client)
    if cancel_check is not None:
        cancel_check()
    if log:
        log("重生成", "检测到要求按最新题目重新生成视频，开始重写全部场景代码")
    extra_code_tasks = [t for t in getattr(intent, "code_tasks", ()) or () if not _is_explicit_source_regen(t)]
    regen_source = effective_source
    if extra_code_tasks:
        merged_meta = dict(effective_source.question_meta or {})
        merged_meta["edit_extra_instructions"] = extra_code_tasks
        regen_source = dataclasses.replace(effective_source, question_meta=merged_meta)
    try:
        generated = generate_with_repair(
            source=regen_source, client=client, output_dir=attempt,
            fps=fps, log=log, phase=phase, images=source_images,
            watermark_style=watermark_style, cancel_check=cancel_check,
        )
    except SceneRepairFailed as exc:
        raise EditError(str(exc)[:400]) from exc

    effective_contract_source_sha256 = contract_source_sha256 or effective_source.source_sha256
    built_meta = {
        **(contract.meta or {}),
        "question_sha256": effective_source.question_sha256,
        "source_sha256": effective_contract_source_sha256,
        "generation": generated.tokens,
        "attempts": [item.to_dict() for item in generated.attempts],
    }
    built = build_contract(
        generated, question=effective_source.problem, fps=fps,
        extra_meta=built_meta,
    )
    problems = validate_contract(built)
    if problems:
        raise EditError("; ".join(str(item) for item in problems))
    built.write(attempt / "scene_contract.json")

    if phase:
        phase("按最新题目渲染视频")
    if log:
        log("渲染", "正在依据最新题目渲染新版视频")

    def render_attempt(folder: Path) -> dict:
        return render_code_lesson(
            folder, folder / "latest.mp4",
            folder / "latest_manifest.json", folder / "latest.srt",
            fps=fps, cache_dir=shared_render_cache(session),
            voice=new_voice, speech_rate=new_rate,
            speech_pitch=old_pitch, speech_volume=old_volume,
            subtitle_style=style, voice_rules=selected_voice_rules,
            watermark_style=watermark_style,
            cancel_check=cancel_check, progress=progress,
        )

    try:
        report = render_attempt(attempt)
    except EngineError as exc:
        if not repairable_render_error(exc):
            raise
        attempt, report = repair_rendered_lesson(
            source=effective_source, current=attempt,
            attempts=attempt / "runtime_repair",
            client=client, fps=fps, original_error=exc,
            render_candidate=render_attempt,
            watermark_style=watermark_style,
            images=source_images, log=log, cancel_check=cancel_check,
        )
        built = SceneContract.read(attempt / "scene_contract.json")

    seconds = round(time.monotonic() - started, 2)
    stats = usage_delta(before, usage_snapshot(client))
    scene_names = [Path(s.path).stem for s in built.scenes]
    task_ledger = [
        {"task": "按最新题目重生成视频", "kind": "regenerate", "status": "applied"},
        *({"task": t, "kind": "code", "status": "applied"} for t in extra_code_tasks),
        *({"task": t, "kind": "subtitle", "status": "applied"} for t in (getattr(intent, "subtitle_tasks", ()) or ())),
        *([{"task": f"音色={new_voice}", "kind": "voice", "status": "applied"}] if getattr(intent, "voice", None) else []),
        *([{"task": f"语速={new_rate}", "kind": "rate", "status": "applied"}] if (getattr(intent, "speech_rate", None) or getattr(intent, "speech_rate_delta", None) is not None) else []),
        *({"task": t, "kind": "ignored", "status": "ignored"} for t in intent.ignored),
    ]
    record = {
        "revision": revision,
        "instruction": instruction,
        "at": int(time.time()),
        "rounds": len(generated.attempts),
        "seconds": seconds,
        "tokens": stats,
        "modified_files": scene_names,
        "target_files": scene_names,
        "scene_order": scene_names,
        "scene_structure": "regenerate_from_source",
        "ignored": list(intent.ignored),
        "voice": new_voice,
        "speech_rate": new_rate,
        "subtitle_style": style,
        "subtitle_tasks": list(intent.subtitle_tasks),
        "removed_scenes": [],
        "ignored_tasks": list(intent.ignored),
        "task_ledger": task_ledger,
        "cache": report.get("cache") or {},
        "scenes": list(report.get("scenes") or ()),
        "source_synced": True,
    }
    (attempt / "edit_record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "revision": revision, "candidate": str(attempt),
        "rounds": len(generated.attempts), "seconds": seconds, "tokens": stats,
        "report": report, "voice": new_voice, "speech_rate": new_rate,
        "record": record,
        "source_synced": True,
        "synced_source_sha256": effective_contract_source_sha256,
        "synced_reference_solution": effective_source.reference_solution,
    }


def run_scene_edit(session: Path, *, instruction: str, client, fps: int,
                   voice: str, speech_rate: str | None = None,
                   speech_pitch: str | None = None,
                   speech_volume: str | None = None,
                   voice_rules: dict | None = None,
                   images: list[str] | None = None,
                   latest_source: LessonSource | None = None,
                   contract_source_sha256: str = "",
                   source_reference_images: tuple[str, ...] = (),
                   source_modified: bool = False,
                   log=None, phase=None, cancel_check=None,
                   progress=None, watermark_style: dict | None = None) -> dict:
    """生成并验证下一版候选；此函数不切换当前版本。

    images 是用户随微调提交的参考图，按顺序交给模型作为视觉参考。
    progress 是渲染引擎的进度回调（阶段 + 已渲染帧数），微调里那次渲染同样
    要能逐帧回写，否则界面上只有一个不动的百分比。
    """
    reference_images = list(dict.fromkeys(str(p) for p in (*source_reference_images, *(images or ())) if str(p)))
    session = Path(session)
    state = _read_state(session)
    current = _current_version(session, state)
    contract = SceneContract.read(current / "scene_contract.json")
    sources = read_scene_sources(current, contract)
    if not sources:
        raise EditError("EDIT_SCENE_CODE_MISSING")

    effective_question = latest_source.problem if latest_source is not None else contract.question
    effective_solution = (
        latest_source.reference_solution
        if latest_source is not None
        else str(state.get("reference_solution") or "")
    )
    effective_answer = latest_source.answer if latest_source is not None else ""
    effective_contract = (
        dataclasses.replace(contract, question=effective_question)
        if effective_question != contract.question
        else contract
    )

    old_voice, old_rate = _previous_audio(current, voice)
    cue_index = [
        {"id": cue.cue_id, "scene": cue.scene_id,
         "text": cue.text[:250], "math": cue.math[:200]}
        for cue in contract.cues
    ]
    try:
        intent = route_instruction_semantic(
            instruction, client=client, sources=sources,
            question=effective_question, cue_index=cue_index,
            previous_question=(contract.question if source_modified else ""),
            source_modified=source_modified,
            current_speech_rate=old_rate)
    except ValueError as exc:
        raise EditError(str(exc)) from exc
    if not intent.actionable:
        # 超出微调能力的请求不再报错，直接"不改"（任务仍算成功）。
        raise EditNoChange(
            "这条要求不在微调范围内，未修改任何内容："
            + "；".join(intent.ignored)[:180])

    new_voice = intent.voice or old_voice
    resolved_rate = resolve_speech_rate(
        old_rate, intent.speech_rate, getattr(intent, "speech_rate_delta", None)
    )
    new_rate = resolved_rate or (speech_rate if speech_rate else old_rate)
    try:
        manifest = json.loads((current / "latest_manifest.json").read_text(encoding="utf-8"))
        previous_style = normalize_subtitle_style(manifest.get("subtitle_style"))
        old_pitch = speech_pitch or str((manifest.get("voice") or {}).get("pitch") or "+0Hz")
        old_volume = speech_volume or str((manifest.get("voice") or {}).get("volume") or "+0%")
        style = apply_subtitle_instructions(
            previous_style, intent.subtitle_tasks,
            tuple(scene.scene_id for scene in contract.scenes),
            tuple(cue.cue_id for cue in contract.cues),
            structured=getattr(intent, "subtitle_style_patch", None),
        )
    except (OSError, TypeError, ValueError) as exc:
        raise EditError("EDIT_SUBTITLE_STYLE_INVALID: " + str(exc)[:180]) from exc
    config_changed = (
        new_voice != old_voice or new_rate != old_rate or style != previous_style
    )
    # 全局发音词典后来即使改变，也不能在一次无关的板书、切幕或字幕微调时
    # 悄悄重写整节课口播。沿用上一成片的规则；精确发音修正通过当前 cue 的
    # tts_text 独立落在源码里，不需要影响其他 cue。
    selected_voice_rules = manifest.get("voice_rules")
    if selected_voice_rules is None:
        selected_voice_rules = voice_rules
    if not intent.requires_ai and not config_changed:
        # 比如"字幕颜色改成红色"这种要求没被识别出来：不改、不报错。
        raise EditNoChange("视频配置与当前版本相同，未修改任何内容")

    revision = int(state["revision"]) + 1
    # 同一修订号的取消任务与重新排队任务绝不共用候选路径。
    attempt = session / "attempts" / f"{revision:04d}-{uuid.uuid4().hex[:12]}"
    # 无匹配对象或无实质变化时不创建任何候选文件夹。
    # 确认要渲染后再由 scenes_dir.mkdir(parents=True) 建立目录。

    if intent.regenerate_from_source:
        if client is None:
            raise EditError("EDIT_AI_CONFIGURATION_REQUIRED")
        regen_source = latest_source or prepare_lesson_source(
            effective_question or "见题干讲解",
            effective_solution or "见题干讲解",
            effective_answer,
        )
        regen_images = tuple(source_reference_images) or tuple(reference_images)
        return _regenerate_from_latest_source(
            session, attempt=attempt, revision=revision,
            instruction=instruction, effective_source=regen_source,
            contract_source_sha256=contract_source_sha256,
            client=client, fps=fps, contract=contract,
            source_images=regen_images,
            new_voice=new_voice, new_rate=new_rate,
            old_pitch=old_pitch, old_volume=old_volume,
            style=style, selected_voice_rules=selected_voice_rules,
            watermark_style=watermark_style, intent=intent,
            log=log, phase=phase, cancel_check=cancel_check,
            progress=progress,
        )

    started = time.monotonic()
    before = usage_snapshot(client)
    changed: tuple[str, ...] = ()
    selected: tuple[str, ...] = ()
    checks = 0
    updated = dict(sources)

    # 删除整幕由 AI 语义理解并给出现有文件名；不再依赖“第 X 幕”正则，
    # 因此“删除最后的总结场景”“删掉含某图像的那一幕”同样可被定位。
    removed = tuple(intent.remove_scene_files)
    if removed and len(updated) - len(removed) < 1:
        raise EditError("EDIT_CANNOT_REMOVE_ALL_SCENES")
    for name in removed:
        updated.pop(name)
        if log:
            log("删场景", f"按用户要求移除 {name}.py（剩 {len(updated)} 幕）")
    structure = intent.scene_structure
    ai_tasks = tuple(intent.code_tasks)
    if structure in ("insert", "split", "merge") and not ai_tasks:
        ai_tasks = (instruction,)
    if ai_tasks and client is None:
        raise EditError("EDIT_AI_CONFIGURATION_REQUIRED")

    if log:
        if intent.ignored:
            # 只报条数：把用户原话整段贴进日志，一条就能占满三行
            log("分流", f"忽略 {len(intent.ignored)} 条与视频无关的要求")
        if config_changed:
            log("配置", f"目标音色 {new_voice}；目标语速 {new_rate}")

    structure_changed = False
    unmatched_tasks: list[str] = []
    if ai_tasks:
        if phase:
            phase("定位需修改的场景")
        try:
            targets = locate_scenes(
                ai_tasks, effective_contract, sources, client,
                structure_action=structure, original_instruction=instruction,
                source_modified=source_modified,
                previous_question=(contract.question if source_modified else ""),
                reference_solution=effective_solution)
        except ValueError as exc:
            raise EditError(str(exc)) from exc
        # 合并场景时也要让模型读取被合并进去的完整源码，
        # 否则它只看得到留下的文件，容易漏掉口播和板书。
        selected = tuple(
            name for name in targets.scenes
            if name not in removed or structure == "merge")
        if structure == "merge":
            selected = tuple(dict.fromkeys((*selected, *removed)))
        if not selected:
            # 找不到目标不能静默扩大为全局；只保留其他明确的参数改动。
            if structure in ("insert", "split", "merge"):
                raise EditError("EDIT_STRUCTURE_TARGET_UNRESOLVED")
            if not removed and not config_changed:
                raise EditNoChange("未在当前视频代码中定位到匹配修改对象，不修改源码")
            unmatched_tasks = list(ai_tasks)
            ai_tasks = ()
            if log:
                log("定位", "没有匹配的代码目标，已明确记录未匹配指令，仅应用其余配置修改")
        if log:
            log("定位", "目标场景 " + ", ".join(selected))
            if intent.voice_only:
                log("校验", "本次仅修正读音：只允许改朗读 tts_text，板书与字幕不动")
        if selected:
            allow_new = structure in ("insert", "split")
            target_scene_ids = {
                scene.scene_id for scene in contract.scenes
                if Path(scene.path).stem in selected
            }
            prior_layout_warnings = manifest_layout_warnings(
                manifest, target_scene_ids)
            errors = ""
            for round_index in range(1, MAX_EDIT_ROUNDS + 1):
                if cancel_check is not None:
                    cancel_check()
                checks = round_index
                if phase:
                    phase(f"精准修改代码（第 {round_index}/{MAX_EDIT_ROUNDS} 轮）")
                payload = edit_payload(
                    ai_tasks, effective_contract, sources, selected,
                    reference_solution=effective_solution,
                    answer=effective_answer,
                    previous_question=(contract.question if source_modified else ""),
                    source_modified=source_modified,
                    errors=errors, reference_images=tuple(reference_images),
                    watermark_style=watermark_style, voice_rules=selected_voice_rules,
                    instruction=instruction, allow_new=allow_new,
                    previous_layout_warnings=prior_layout_warnings,
                    voice_only=intent.voice_only)
                response = invoke_scene_model(
                    client, system=editor_system_prompt(), user_json=payload,
                    timeout=1800, images=reference_images or None,
                )
                answer = response.text
                if answer.strip().upper() == "NO_MATCH":
                    if not removed and not config_changed:
                        raise EditNoChange("AI 在当前源码中未发现需要修改的对象")
                    break
                try:
                    candidate, modified = merge_targeted_sources(
                        sources, answer, selected, allow_new=allow_new)
                    if allow_new and not (set(candidate) - set(sources)):
                        raise EditOutputError("EDIT_STRUCTURE_EXPECTED_NEW_SCENE")
                    if structure != "none":
                        # 先移除用户明确授权合并/删除的场景，再按语义重排。
                        for name in removed:
                            candidate.pop(name, None)
                        candidate = order_edited_scenes(
                            candidate, instructions=(instruction,), client=client,
                            previous_order=tuple(sources),
                            preserve_relative_existing=structure != "reorder",
                            reorder_requested=structure == "reorder",
                        )
                    if not modified:
                        raise EditOutputError("EDIT_NO_EFFECT_ON_REQUESTED_TARGETS")
                    if intent.voice_only:
                        # 只改读音：除 tts_text 外的任何源码变化都退回重做，
                        # 保证板书、字幕文字、动画与切幕一行都不动。
                        assert_only_tts_text_changed(sources, candidate)
                    else:
                        validate_edit_scope_ast(
                            sources, candidate, targets=selected, allow_new=allow_new, allowed_removed=removed)
                    for name in removed:
                        candidate.pop(name, None)
                    problems = _validate_sources(
                        candidate, question=effective_question,
                        reference_solution=effective_solution)
                    if problems:
                        raise EditOutputError("\n".join(problems)[:2200])
                    sync_contract_now = bool(intent.syncs_question_source and latest_source is not None)
                    effective_contract_source_sha256 = (
                        contract_source_sha256
                        or (latest_source.source_sha256 if latest_source is not None else "")
                    )
                    round_question = effective_question if (sync_contract_now or not source_modified) else contract.question
                    round_meta = dict(contract.meta)
                    if sync_contract_now and latest_source is not None:
                        round_meta["source_sha256"] = effective_contract_source_sha256
                        round_meta["question_sha256"] = latest_source.question_sha256
                    built = build_contract(
                        _AsGenerated(candidate), question=round_question,
                        fps=fps, extra_meta=round_meta)
                    problems = validate_contract(built)
                    if problems:
                        raise EditOutputError("; ".join(str(item) for item in problems))
                    updated, changed = candidate, modified
                    structure_changed = tuple(candidate) != tuple(sources)
                    if log:
                        log("校验", f"第 {round_index} 轮通过，实改 {len(changed)} 个文件")
                    break
                except (EditOutputError, ValueError, RuntimeError) as exc:
                    errors = str(exc)[:2400]
                    if log:
                        # 运行日志只给中文：错误码与英文原文统一翻译后再写。
                        from ..services.jobs import failure_text
                        log("校验", f"第 {round_index} 轮未通过："
                                    f"{failure_text(RuntimeError(errors))}")
            else:
                raise EditError(
                    f"EDIT_REPAIR_EXHAUSTED: {MAX_EDIT_ROUNDS} 轮失败：{errors[:380]}")

    if structure == "reorder" and not structure_changed:
        reordered = order_edited_scenes(
            updated, instructions=(instruction,), client=client,
            previous_order=tuple(sources), reorder_requested=True)
        structure_changed = structure_changed or tuple(reordered) != tuple(updated)
        updated = reordered


    if not changed and not removed and not config_changed and not structure_changed:
        # 模型返回了代码但和原来完全一样（例如要求超出了能力）：不渲染、不失败。
        raise EditNoChange("模型没有产生实际改动，未修改任何内容")

    if cancel_check is not None:
        cancel_check()
    # 不变的场景完整复制；带改动的场景仅替换目标文件。
    scenes_dir = attempt / "scenes"
    scenes_dir.mkdir(parents=True)
    for name, code in updated.items():
        (scenes_dir / f"{name}.py").write_text(
            code.rstrip() + "\n", encoding="utf-8")

    # A configuration-only edit still rebuilds the index at the current 60 FPS.
    # No AI code is modified and unchanged Manim source hashes are preserved.
    source_synced = bool(
        intent.syncs_question_source and latest_source is not None
        and (changed or removed or structure_changed)
    )
    final_question = effective_question if (source_synced or not source_modified) else contract.question
    effective_contract_source_sha256 = (
        contract_source_sha256
        or (latest_source.source_sha256 if latest_source is not None else "")
    )
    final_meta = dict(contract.meta)
    if source_synced and latest_source is not None:
        final_meta["source_sha256"] = effective_contract_source_sha256
        final_meta["question_sha256"] = latest_source.question_sha256
    built = build_contract(
        _AsGenerated({
            name: code.rstrip() + "\n" for name, code in updated.items()
        }), question=final_question, fps=fps, extra_meta=final_meta)
    previous_cues = {cue.cue_id: cue for cue in contract.cues}
    for cue in built.cues:
        previous_cue = previous_cues.get(cue.cue_id)
        if previous_cue and cue.caption_text != previous_cue.caption_text:
            style["text_overrides"].pop(cue.cue_id, None)
    built.write(attempt / "scene_contract.json")

    if phase:
        phase("复用未改变的场景，渲染最新视频")
    if log:
        log("渲染", "增量渲染：优先命中初始视频共用的缓存")
    def render_attempt(folder: Path) -> dict:
        return render_code_lesson(
            folder, folder / "latest.mp4",
            folder / "latest_manifest.json", folder / "latest.srt",
            fps=fps, cache_dir=shared_render_cache(session),
            voice=new_voice, speech_rate=new_rate,
            speech_pitch=old_pitch, speech_volume=old_volume,
            subtitle_style=style, voice_rules=selected_voice_rules,
            watermark_style=watermark_style,
            cancel_check=cancel_check, progress=progress,
        )

    try:
        report = render_attempt(attempt)
    except EngineError as exc:
        if not changed and not removed and not structure_changed:
            # 纯参数修改并不授权改动教学代码，不能为了修环境异常编辑整节课。
            raise
        attempt, report = recover_edited_render(
            attempt=attempt, source_before=sources,
            tasks=ai_tasks, instruction=instruction, editable_files=changed or selected, client=client,
            fps=fps, render=render_attempt, original_error=exc,
            reference_solution=effective_solution,
            question=final_question, answer=effective_answer,
            previous_question=(contract.question if source_modified else ""),
            source_modified=source_modified,
            watermark_style=watermark_style, voice_rules=selected_voice_rules,
            images=reference_images,
            voice_only=intent.voice_only,
            log=log, cancel_check=cancel_check,
        )
        # 记录以真正成功渲染的源码为准，而非最初渲染失败的草稿。
        final_contract = SceneContract.read(attempt / "scene_contract.json")
        final_sources = read_scene_sources(attempt, final_contract)
        if intent.voice_only:
            assert_only_tts_text_changed(sources, final_sources)
        changed = tuple(name for name, code in final_sources.items()
                        if sources.get(name) != code)
        updated = final_sources
    seconds = round(time.monotonic() - started, 2)
    stats = usage_delta(before, usage_snapshot(client))
    task_ledger = [
        *({"task": t, "kind": "code", "status": "applied"} for t in ai_tasks),
        *({"task": t, "kind": "code", "status": "unmatched"} for t in unmatched_tasks),
        *({"task": t, "kind": "subtitle", "status": "applied"} for t in intent.subtitle_tasks),
        *([{"task": f"音色={new_voice}", "kind": "voice", "status": "applied"}] if intent.voice else []),
        *([{"task": f"语速={new_rate}", "kind": "rate", "status": "applied"}] if (intent.speech_rate or getattr(intent, "speech_rate_delta", None) is not None) else []),
        *({"task": f"删幕:{n}", "kind": "remove_scene", "status": "applied"} for n in removed),
        *([{"task": f"结构:{structure}", "kind": "structure", "status": "applied"}] if structure != "none" else []),
        *({"task": t, "kind": "ignored", "status": "ignored"} for t in intent.ignored),
    ]
    record = {
        "revision": revision,
        "instruction": instruction,
        "at": int(time.time()),
        "rounds": checks,
        "seconds": seconds,
        "tokens": stats,
        "modified_files": list(changed),
        "target_files": list(selected),
        "scene_order": list(updated),
        "scene_structure": structure,
        "ignored": list(intent.ignored),
        "unmatched_tasks": unmatched_tasks,
        "task_ledger": task_ledger,
        "voice": new_voice,
        "speech_rate": new_rate,
        "subtitle_style": style,
        "subtitle_tasks": list(intent.subtitle_tasks),
        "removed_scenes": list(removed),
        "ignored_tasks": list(intent.ignored),
        "cache": report.get("cache") or {},
        "scenes": list(report.get("scenes") or ()),
        "source_synced": source_synced,
    }
    (attempt / "edit_record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    out = {
        "revision": revision, "candidate": str(attempt),
        "rounds": checks, "seconds": seconds, "tokens": stats,
        "report": report, "voice": new_voice, "speech_rate": new_rate,
        "record": record,
        "source_synced": source_synced,
    }
    if source_synced and latest_source is not None:
        out["synced_source_sha256"] = effective_contract_source_sha256
        out["synced_reference_solution"] = latest_source.reference_solution
    return out





__all__ = [
    "EditError", "STATE_SCHEMA", "create_session", "latest_paths",
    "shared_render_cache", "synchronize_session_revision",
    "run_scene_edit", "complete_session_publish",
    "record_feedback", "export_history", "update_state_source",
]
