"""渲染阶段：语音 → 沙箱渲染场景代码 → 字幕/水印 → mp4，并建立微调会话。"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from animation_engine.code.scene_contract import SceneContract
from ...api.config_store import (
    stored_default_voice, stored_subtitle_style, stored_voice_rules,
    stored_watermark_style,
)
from ...api.source_guard import verified_contract, active_scene_folder

from animation_engine.render.code_scene_render import render_code_lesson
from animation_engine.errors import EngineError
from ...ai.model_hub import task_client
from ...pipeline.runtime_render_repair import (
    repair_rendered_lesson, repairable_render_error,
)
from ...pipeline.source_assets import (
    SourceInputError, lesson_question_meta, prepare_lesson_source,
)

from ...api.storage import (
    lesson_get, render_cache_root, resolve_lesson_root, video_output_root,
)
from ...core.models import EditSessionArchive, Job
from ...pipeline.scene_edit import create_session, update_state_source
from ...pipeline.scene_figures import load_reference_figures
from ..jobs import job_log
from ..job_reporting import JobReporter, STAGE_TEXT
from ..task_control import assert_running




def run(ctx, state) -> None:
    SessionLocal = ctx.SessionLocal
    lesson_id = state.lesson_id
    job_id = state.job_id
    previous_revision = state.previous_revision
    fps = state.fps
    folder = state.folder

    contract_path = folder / "scene_contract.json"
    if not contract_path.is_file():
        raise RuntimeError("SCENE_CONTRACT_MISSING: 请先生成场景代码")

    with SessionLocal() as db:
        lesson = lesson_get(db, lesson_id)
        job = db.get(Job, job_id)
        # 语音模块里选的音色是全局权威：没有单独指定时才回退到题目上的默认值。
        voice = stored_default_voice(ctx) or "zh-CN-XiaoxiaoNeural"
        source_folder = active_scene_folder(lesson, folder)
        # PostgreSQL course configuration is authoritative even when a previous
        # manifest exists. Reusing old manifest rate/pitch would undo user edits.
        prior_rate = lesson.speech_rate or "+5%"
        prior_pitch = lesson.speech_pitch or "+0Hz"
        prior_volume = lesson.speech_volume or "+0%"
        # 指纹校验统一放到下面的「校准之后再校验」一处：题库正文改过、
        # 但 source_sha256 字段滞后的记录不能在这里被误判成源码过期。
        job.phase = "渲染画面与音频"
        db.commit()

    output = video_output_root(ctx.root, lesson_id) / job_id
    movie = output / "latest.mp4"
    manifest = output / "latest_manifest.json"
    srt = output / "latest.srt"
    # Historical 30-FPS source stays untouched. Only a new work copy is
    # normalized to 60 before a new video is produced.
    # Second check at the worker boundary, not just the HTTP entrypoint.
    with SessionLocal() as vdb:
        current_lesson = lesson_get(vdb, lesson_id)
        verified_contract(current_lesson, source_folder)
        # 校验通过后再把滞后的数据库指纹按当前权威正文校准，避免校验失败前脏写 DB。
        try:
            fresh = prepare_lesson_source(
                current_lesson.problem, current_lesson.reference_solution,
                getattr(current_lesson, "answer", "") or "")
        except SourceInputError:
            fresh = None
        if fresh is not None and current_lesson.source_sha256 != fresh.source_sha256:
            current_lesson.source_sha256 = fresh.source_sha256
            vdb.commit()
            job_log(vdb, vdb.get(Job, job_id), "输入",
                    "题库指纹已按当前正文校准（原记录滞后）")
    source_contract = SceneContract.read(source_folder / "scene_contract.json")
    if source_contract.fps != 60:
        fixed = output / "source_60fps"
        if fixed.exists():
            shutil.rmtree(fixed)
        fixed.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_folder / "scenes", fixed / "scenes")
        SceneContract.build(
            question=source_contract.question, fps=60,
            scenes=source_contract.scenes, cues=source_contract.cues,
            meta=source_contract.meta,
        ).write(fixed / "scene_contract.json")
        source_folder = fixed

    reporter = JobReporter(SessionLocal, job_id)
    render_progress = reporter.media_progress

    # Existing video re-renders reuse its subtitle style; brand new videos use
    # the persisted global default. Never edit previously published manifests.
    subtitle_style = stored_subtitle_style(ctx)
    if lesson.latest_manifest and Path(lesson.latest_manifest).is_file():
        prev = json.loads(Path(lesson.latest_manifest).read_text(encoding="utf-8"))
        subtitle_style = prev.get("subtitle_style") or subtitle_style
    # 已保存视频保持原版本字幕样式；新视频使用数据库中的默认值。
    started = time.monotonic()
    # 水印统一以全局配置为准：历史成片里残留的「本课无水印」标记不再生效，
    # 保证以后每一版出片都带右上角水印。
    watermark_style = stored_watermark_style(ctx)
    voice_rules = stored_voice_rules(ctx)

    def render_from(source_dir: Path) -> dict:
        return render_code_lesson(
            source_dir, movie, manifest, srt,
            fps=fps, cache_dir=render_cache_root(ctx.root),
            progress=render_progress, voice=voice, speech_rate=prior_rate,
            speech_pitch=prior_pitch, speech_volume=prior_volume,
            subtitle_style=subtitle_style,
            watermark_style=watermark_style,
            voice_rules=voice_rules,
            cancel_check=lambda: assert_running(SessionLocal, job_id),
        )

    published_ok = False
    try:
        try:
            report = render_from(source_folder)
        except EngineError as exc:
            if not repairable_render_error(exc):
                raise
            # 静态 AST/契约通过不意味着 Manim 在沙箱里能够执行；
            # 只对真实场景代码报错自动修复，绝不拿 TTS/网络故障让 AI 改数学。
            with SessionLocal() as repair_db:
                repair_client = task_client(repair_db, "generate")
                fresh = lesson_get(repair_db, lesson_id)
                repair_source = prepare_lesson_source(
                    fresh.problem, fresh.reference_solution, fresh.answer or "",
                    meta=lesson_question_meta(fresh))
                reference_images=tuple(load_reference_figures(fresh.image_refs or ""))
            if repair_client is None or not hasattr(repair_client, "generate_text"):
                raise RuntimeError(
                    "RUNTIME_REPAIR_AI_NOT_CONFIGURED: 渲染失败且无可用生成模型"
                ) from exc
            repaired_folder, report = repair_rendered_lesson(
                source=repair_source, current=source_folder,
                attempts=output / "runtime_repair_attempts",
                client=repair_client, fps=fps, original_error=exc,
                render_candidate=render_from, watermark_style=watermark_style,
                images=reference_images,
                log=reporter.log,
                cancel_check=lambda: assert_running(SessionLocal, job_id),
            )
            source_folder = repaired_folder
            # 将运行期修复通过的源码同步回课程根目录（仅当原目录与此次出片同源且非独立会话），
            # 避免下次重新渲染或查看代码时仍读到修复前的旧坏源码。
            try:
                if repaired_folder != folder and (repaired_folder / "scenes").is_dir():
                    scenes_dst = folder / "scenes"
                    if scenes_dst.exists():
                        shutil.rmtree(scenes_dst)
                    shutil.copytree(repaired_folder / "scenes", scenes_dst)
                    if (repaired_folder / "scene_contract.json").is_file():
                        shutil.copy2(repaired_folder / "scene_contract.json",
                                     folder / "scene_contract.json")
            except OSError:
                pass

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
            session = folder / "edit_sessions" / job_id
            if not session.exists():
                create_session(source_folder, movie, manifest, srt, session)
                update_state_source(session, lesson.reference_solution or "")
            lesson.fps = 60
            lesson.latest_video = str(movie)
            lesson.latest_manifest = str(manifest)
            lesson.session_path = str(session)
            lesson.video_source_sha256 = lesson.source_sha256
            db.add(EditSessionArchive(
                lesson_id=lesson_id, job_id=job_id,
                session_path=str(session), source_revision=previous_revision,
            ))
            lesson.revision += 1
            lesson.status = "ready"
            lesson.video_review_status = "pending"
            lesson.video_reviewed_at = None
            job.status = "succeeded"
            job.phase = "完成"
            job.progress = 100
            job.frames_done = job.frames_total or job.frames_done
            job_log(db, job, "完成", "输出完毕（视频已生成，可预览、下载或微调）")
            db.commit()
        published_ok = True
    finally:
        # 清理中间 work 目录与失败任务的孤立大文件产物，避免磁盘膨胀。
        for candidate_dir in (folder / "work", source_folder / "work"):
            if candidate_dir.exists():
                shutil.rmtree(candidate_dir, ignore_errors=True)
        if not published_ok:
            for orphan in (output / "source_60fps", output / "runtime_repair_attempts",
                           movie, manifest, srt):
                try:
                    if orphan.is_dir():
                        shutil.rmtree(orphan, ignore_errors=True)
                    elif orphan.is_file():
                        orphan.unlink(missing_ok=True)
                except OSError:
                    pass

    # 只留「当前版 + 上一版」：新版出片成功后清掉更早的成片目录。
    # 必须在 commit 之后做：删的是别的任务目录，删早了会留下悬空指针。
    try:
        from ..retention import prune_lesson_versions
        prune_lesson_versions(folder, protected=(str(output), str(movie), str(session)))
        prune_lesson_versions(output.parent, protected=(str(output), str(movie), str(session)))
    except Exception:
        # 清理失败只是占点磁盘，绝不能影响已经出好的片子
        pass
