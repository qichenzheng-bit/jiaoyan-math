"""微调任务：从最新成功版本局部修改；发布前核对数据库修订号。"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from ...api.config_store import stored_default_voice, stored_voice_rules, stored_watermark_style

from ...api.storage import lesson_get
from ...core.models import EditRecord, Job, Lesson
from ...core.solution_methods import recommended_solution
from ...pipeline.edit_publisher import promote_candidate
from ...pipeline.scene_edit import (
    EditError, EditNoChange, complete_session_publish, run_scene_edit,
    synchronize_session_revision, update_state_source,
)
from ...pipeline.scene_figures import load_reference_figures
from ...pipeline.source_assets import lesson_question_meta, prepare_lesson_source, knowledge_envelope
from ..jobs import failure_text, job_log, log_token_usage, usage_totals
from ..job_reporting import JobReporter
from ..task_control import assert_running


def run_edit(ctx, state) -> None:
    SessionLocal = ctx.SessionLocal
    job_id, lesson_id, edit_id = state.job_id, state.lesson_id, state.edit_id
    previous_revision = state.previous_revision
    selected_model = state.selected_model
    cursor = state.progress.cursor

    with SessionLocal() as db:
        lesson = lesson_get(db, lesson_id)
        record = db.get(EditRecord, edit_id) if edit_id else None
        job = db.get(Job, job_id)
        if record is None:
            raise RuntimeError("EDIT_RECORD_MISSING")
        instruction = record.original_instruction or ""
        # 参考图路径（JSON 数组）；脏数据当成没有图
        try:
            reference_images = [str(p) for p in json.loads(record.images or "[]")
                                if isinstance(p, str)]
        except ValueError:
            reference_images = []
        latest_problem = lesson.problem
        latest_solution = (lesson.reference_solution if knowledge_envelope(lesson.reference_solution) is not None
                           else recommended_solution(lesson.reference_solution))
        latest_answer = getattr(lesson, "answer", "") or ""
        latest_meta = lesson_question_meta(lesson)
        latest_source_images = tuple(load_reference_figures(getattr(lesson, "image_refs", "") or ""))
        latest_source = prepare_lesson_source(
            latest_problem, latest_solution, latest_answer, meta=latest_meta)
        authoritative_source_sha256 = prepare_lesson_source(
            latest_problem, lesson.reference_solution, latest_answer, meta=latest_meta
        ).source_sha256
        source_modified = bool(
            getattr(lesson, "video_source_sha256", None)
            and (lesson.source_sha256 or "") != lesson.video_source_sha256
        )
        session = Path(lesson.session_path or "")
        latest_video = Path(lesson.latest_video) if lesson.latest_video else None
        voice = stored_default_voice(ctx) or lesson.voice or "zh-CN-XiaoxiaoNeural"
        lesson_speech_rate = lesson.speech_rate or ""
        lesson_speech_pitch = lesson.speech_pitch or ""
        lesson_speech_volume = lesson.speech_volume or ""
        fps = state.fps
        job.phase = "识别微调要求"
        job_log(db, job, "微调", "已收到修改要求")
        db.commit()

    if not session.is_dir():
        raise RuntimeError("EDIT_SESSION_MISSING")
    synchronize_session_revision(session, latest_video)
    # 水印统一以全局配置为准：旧版本里「本课无水印」的记录不再沿用，
    # 微调产出的新版本也带右上角水印。
    edit_watermark_style = stored_watermark_style(ctx)

    before = usage_totals(selected_model)
    cursor.update(base=5, ceiling=55, chars=0, label="智能定位与精准微调")

    reporter = JobReporter(SessionLocal, job_id)
    log, phase = reporter.log, reporter.phase

    def render_progress(info):
        reporter.media_progress(info, microtune=True)

    try:
        try:
            outcome = run_scene_edit(
                session, instruction=instruction, client=selected_model,
                fps=60, voice=voice,
                speech_rate=lesson_speech_rate or None,
                speech_pitch=lesson_speech_pitch or None,
                speech_volume=lesson_speech_volume or None,
                images=reference_images,
                latest_source=latest_source,
                contract_source_sha256=authoritative_source_sha256,
                source_reference_images=latest_source_images,
                source_modified=source_modified,
                voice_rules=stored_voice_rules(ctx),
                watermark_style=edit_watermark_style,
                log=log, phase=phase, progress=render_progress,
                cancel_check=lambda: assert_running(SessionLocal, job_id))
        except EditNoChange as exc:
            # 超出微调能力 / 算下来没有任何变化：不改、不失败、不动已发布的视频。
            reason = str(getattr(exc, "reason", "") or exc)[:300]
            with SessionLocal() as db:
                # 与正常发布路径相同：锁住来源版本，再校验任务是否仍在运行。
                # 不能让一个已经取消的任务把对应微调记录写回 preview_ready。
                lesson = db.scalar(
                    select(Lesson).where(Lesson.id == lesson_id).with_for_update())
                job = db.get(Job, job_id)
                record = db.get(EditRecord, edit_id) if edit_id else None
                if (lesson is None or lesson.deleted_at is not None
                        or lesson.revision != previous_revision
                        or job is None or job.status != "running"
                        or record is None or record.status not in ("queued", "running")):
                    raise RuntimeError("STALE_OR_CANCELLED_JOB")
                job.status = "succeeded"
                job.phase = "完成（未修改）"
                job.progress = 100
                record.status = "preview_ready"
                record.error = "未做任何修改：" + reason
                job_log(db, job, "跳过", reason or "未修改任何内容")
                db.commit()
            return
        except EditError as exc:
            log("失败", failure_text(exc))
            raise RuntimeError(str(exc)) from exc

        cursor.update(base=55, ceiling=95, chars=0, label="验证最新视频并准备发布")
        # 先渲染候选，旧视频保持可用。文件提升至不可变版本后，数据库才切换指针。
        with SessionLocal() as db:
            lesson = db.scalar(
                select(Lesson).where(Lesson.id == lesson_id).with_for_update())
            record = db.get(EditRecord, edit_id) if edit_id else None
            job = db.get(Job, job_id)
            if (lesson is None or lesson.deleted_at is not None or
                    lesson.revision != previous_revision or
                    job is None or job.status != "running"):
                raise RuntimeError("STALE_OR_CANCELLED_JOB")

            version = promote_candidate(
                session, Path(outcome["candidate"]), outcome["revision"])
            lesson.latest_video = str(version / "latest.mp4")
            lesson.latest_manifest = str(version / "latest_manifest.json")
            lesson.voice = outcome["voice"]
            lesson.speech_rate = outcome["speech_rate"]
            lesson.fps = 60
            lesson.revision += 1
            lesson.status = "ready"
            lesson.video_review_status = "pending"
            lesson.video_reviewed_at = None
            if outcome.get("source_synced"):
                synced_sha = outcome.get("synced_source_sha256") or authoritative_source_sha256
                lesson.source_sha256 = synced_sha
                lesson.video_source_sha256 = synced_sha
            elif not getattr(lesson, "video_source_sha256", None):
                lesson.video_source_sha256 = lesson.source_sha256
            if record is not None:
                record.status = "preview_ready"
                record.error = None
                # 结果镜像到独立的微调语言存档（不改动原始语言与分类）
                try:
                    from ...ai import edit_language
                    edit_language.mark_result(db, record.id, "preview_ready", "")
                except Exception:
                    pass
            job.status = "succeeded"
            job.phase = "完成"
            job.progress = 100
            job_log(db, job, "完成",
                    f"最新版视频就绪（第 {outcome['revision']} 轮，{outcome['seconds']}s）")
            db.commit()

        # 数据库的不可变文件指针已经发布。latest 别名及历史索引用于兼容旧入口；
        # 它们异常时不得将已经成功发布的视频误标为失败。
        try:
            complete_session_publish(session, outcome, version)
            if outcome.get("source_synced") and outcome.get("synced_reference_solution") is not None:
                update_state_source(session, outcome["synced_reference_solution"])
        except Exception:
            log("提醒", "视频已发布，但历史索引需要恢复，可在任务列表重新打开一次")

        # 微调同样只留最近两版：会话内 versions/ 只保留最新两轮，
        # 更早的整份会话（含旧成片）也一起清掉。Manim 代码在 classroom/scenes 里，不受影响。
        try:
            from ..retention import prune_lesson_versions
            prune_lesson_versions(state.folder,
                                  protected=(str(Path(version) / "latest.mp4"),
                                             str(session)))
        except Exception:
            pass
    finally:
        log_token_usage(SessionLocal, job_id, selected_model, before)
