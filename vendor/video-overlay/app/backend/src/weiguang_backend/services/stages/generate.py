"""生成阶段：AI 直接写 Manim 场景代码，校验不过就自动修复（最多三轮）。

产物只有两样：
    scenes/<scene>.py          可执行的 Manim 代码
    scene_contract.json        场景索引 + 口播锚点（时间轴原料）

生成成功后自动派发渲染，中间不再有人工审核，也没有 curriculum 任务。
"""
from __future__ import annotations

from pathlib import Path

from ...api.storage import lesson_get, render_cache_root, resolve_lesson_root
from ...api.config_store import stored_watermark_style
from ...core.models import Job
from ...pipeline.scene_codegen import build_contract, usage_snapshot
from ...pipeline.scene_figures import load_reference_figures
from ...pipeline.scene_publish import ScenePublication
from ...pipeline.scene_repair import SceneRepairFailed, generate_with_repair
from ...pipeline.source_assets import (
    SourceInputError, lesson_question_meta, prepare_lesson_source,
    replace_markdown_images_for_prompt, validate_solution_ready_for_video,
)
from ..jobs import job_add, job_log, log_token_usage, usage_totals
from ..job_reporting import JobReporter
from ..task_control import assert_running


def _prepare_generation_sources(lesson):
    """Return the recommended prompt source and full-source contract digest."""
    from ...core.solution_methods import alternative_method_summaries, recommended_solution

    problem = lesson.problem
    answer = getattr(lesson, "answer", "") or ""
    validate_solution_ready_for_video(lesson.reference_solution or "", answer)
    base_meta = lesson_question_meta(lesson)
    authoritative = prepare_lesson_source(
        problem, lesson.reference_solution, answer, meta=base_meta
    )
    alts = alternative_method_summaries(lesson.reference_solution)
    prompt_meta = dict(base_meta, alternative_methods=alts) if alts else base_meta
    prompt_problem = replace_markdown_images_for_prompt(problem)
    prompt_solution = replace_markdown_images_for_prompt(
        recommended_solution(lesson.reference_solution)
    )
    prompt_answer = replace_markdown_images_for_prompt(answer)
    prompt_source = prepare_lesson_source(
        prompt_problem, prompt_solution, prompt_answer, meta=prompt_meta
    )
    return prompt_source, authoritative.source_sha256


def run(ctx, state) -> None:
    SessionLocal = ctx.SessionLocal
    dispatch = ctx.dispatch
    job_id = state.job_id
    lesson_id = state.lesson_id
    previous_revision = state.previous_revision
    fps = state.fps
    selected_model = state.selected_model
    cursor = state.progress.cursor

    folder = resolve_lesson_root(ctx.root, lesson_id)

    with SessionLocal() as db:
        lesson = lesson_get(db, lesson_id)
        try:
            source, contract_source_sha256 = _prepare_generation_sources(lesson)
        except SourceInputError as exc:
            raise RuntimeError(str(exc)) from exc
        # 题图仅交给 AI 参考，禁止生成后覆盖任意 Manim 绘图代码。
        reference_images = load_reference_figures(
            getattr(lesson, "image_refs", "") or "",
            texts=(
                lesson.problem,
                lesson.reference_solution,
                getattr(lesson, "answer", "") or "",
            ),
        )

    import re
    markers={int(n) for text in (source.problem,source.reference_solution,source.answer) for n in re.findall(r'\[参考附图(\d+)\]',text)}
    if markers and (not reference_images or max(markers)>len(reference_images)):
        raise RuntimeError('VIDEO_REFERENCE_FIGURES_MISSING')
    cursor.update(base=2, ceiling=10, chars=0, label="检查输入")

    # Generate to an isolated candidate directory. The previously published
    # scene sources stay intact until the new code and contract pass validation.
    candidate = folder / "generation_attempts" / job_id
    candidate.mkdir(parents=True, exist_ok=True)

    if selected_model is None or not hasattr(selected_model, "generate_text"):
        # 没有可用的生成模型：给出可读错误，而不是 AttributeError。
        raise RuntimeError("GENERATION_AI_NOT_CONFIGURED")

    token_before = usage_totals(selected_model)
    cursor.update(base=10, ceiling=70, chars=0, label="生成 Manim 代码")
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        job.phase = "生成 Manim 代码"
        db.commit()

    reporter = JobReporter(SessionLocal, job_id)
    log, phase = reporter.log, reporter.phase
    tokens_logged = False

    try:
        try:
            generated = generate_with_repair(
                source=source, client=selected_model, output_dir=candidate,
                fps=fps, log=log, phase=phase, images=tuple(reference_images),
                watermark_style=stored_watermark_style(ctx),
                cache_dir=render_cache_root(ctx.root),
                cancel_check=lambda: assert_running(SessionLocal, job_id))
            tokens_logged = True
        except SceneRepairFailed as exc:
            diagnostics = exc.diagnostics or {}
            # 轮数按实际跑的算：可能是三轮跑满，也可能第二轮就判定没有进展，
            # 写死「三轮」会和上面的日志自相矛盾。
            rounds = len(diagnostics.get("rounds") or ())
            log("失败", f"代码修复已停止（共 {rounds} 轮），诊断已保存在 generation.json")
            raise RuntimeError(str(exc)) from exc

        contract = build_contract(
            generated, question=source.problem, fps=fps,
            extra_meta={
                "question_sha256": source.question_sha256,
                "prompt_job_id": job_id,
                "source_sha256": contract_source_sha256,
                "generation": generated.tokens,
                "attempts": [item.to_dict() for item in generated.attempts],
            },
        )
        contract.write(candidate / "scene_contract.json")

        tokens = usage_snapshot(selected_model)
        cursor.update(base=70, ceiling=95, chars=0, label="校验完成")

        with SessionLocal() as db:
            from sqlalchemy import select
            from ...core.models import Lesson
            lesson = db.scalars(
                select(Lesson).where(Lesson.id == lesson_id, Lesson.deleted_at.is_(None)).with_for_update()
            ).first()
            if lesson is None:
                raise RuntimeError("LESSON_NOT_FOUND")
            job = db.get(Job, job_id)
            if lesson.revision != previous_revision or job is None or job.status != "running":
                raise RuntimeError("STALE_OR_CANCELLED_JOB")
            # 源码与契约成对替换；数据库提交失败时可完整回滚。
            publication = ScenePublication(folder, candidate, job_id)
            publication.publish()
            try:
                lesson.status = "generated"
                lesson.source_sha256 = contract_source_sha256
                job.status = "succeeded"
                job.phase = "代码已生成"
                job.progress = 100
                # 生成源码发布与后续渲染入队使用同一事务，避免旧会话微调插队。
                db.flush()
                next_job = job_add(db, lesson, "render", pin_model=False, commit=False)
                next_id = next_job.id
                db.commit()
            except Exception:
                db.rollback()
                publication.rollback()
                raise
    finally:
        log_token_usage(SessionLocal, job_id, selected_model, token_before,
                        write_log=not tokens_logged)

    dispatch(next_id)
