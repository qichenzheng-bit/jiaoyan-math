"""真实 Manim 渲染失败后，依据技术错误最小修复 AI 场景源码。

不审查数学正确性，不修改原始发布目录；只有完整源码/契约/视频
在隔离候选目录中通过校验后，才由渲染任务选用该候选。
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from animation_engine.code.scene_contract import SceneContract
from animation_engine.errors import EngineError
from animation_engine.speech.cue_extract import extract_scenes
from .scene_codegen import build_contract, extract_blocks, system_prompt
from .prompt_bundle import entry, shared_specs, SEP
from . import prompt_bundle
from .scene_model_call import invoke_scene_model
from .scene_output import SceneCodeRejected, read_scene_sources, write_scenes
from .scene_repair_support import _merge, _repair_prompt
from .source_assets import LessonSource

MAX_RUNTIME_REPAIRS = 3
_REPAIRABLE_PREFIXES = (
    "SCENE_RENDER_FAILED", "SCENE_ACTION_AFTER_LAST_CUE",
    "SCENE_ACTION_OVERRUN_AUDIO",
    "SCENE_FRAME_COUNT_MISMATCH", "SCENE_TIMELINE_EMPTY",
    "CAPTION_MATH_NEEDS_REVIEWED_BREAK", "CAPTION_LINE_TOO_LONG", "CAPTION_SAFE_REGION_TOO_SMALL",
)


def repairable_render_error(error: Exception) -> bool:
    """只修 Manim 源码类错误；TTS、网络、FFmpeg 和环境错误不让 AI 乱改代码。"""
    return isinstance(error, EngineError) and str(error).startswith(_REPAIRABLE_PREFIXES)


def _diagnostic(folder: Path, error: Exception) -> str:
    parts = [str(error)]
    for log in sorted((folder / "work").glob("*.error.log")):
        try:
            text = log.read_text(encoding="utf-8")
            if len(text) > 15000:
                text = text[:3000] + "\n...[truncated]...\n" + text[-12000:]
            parts.append(f"[{log.stem}] " + text)
        except OSError:
            pass
    return "\n".join(parts)[-24000:]


_SCENE_NAME_RE = re.compile(r"\b(scene_\d{2,3})\b")
_LINE_NO_RE = re.compile(r"(?:scene_\d{2,3}\.py|File \"[^\"]+\"), line (\d+)")


def _extract_repair_loci(error_text: str, previous: dict[str, str]) -> list[dict]:
    """根据异常日志定位受影响的场景文件、行号范围及周围代码窗口。"""
    mentioned_scenes = [s for s in dict.fromkeys(_SCENE_NAME_RE.findall(error_text)) if s in previous]
    if not mentioned_scenes:
        mentioned_scenes = list(previous)
    lines_hit = sorted({int(m.group(1)) for m in _LINE_NO_RE.finditer(error_text) if int(m.group(1)) > 0})
    loci: list[dict] = []
    for scene_id in mentioned_scenes:
        src_lines = previous[scene_id].splitlines()
        entry: dict = {"scene_id": scene_id}
        if lines_hit:
            win_lines = [ln for ln in lines_hit if ln <= len(src_lines)]
            if win_lines:
                entry["lines"] = win_lines[:6]
                lo = max(1, min(win_lines) - 8)
                hi = min(len(src_lines), max(win_lines) + 8)
                entry["focus_window"] = f"L{lo}-L{hi}"
        loci.append(entry)
    return loci


def _cues_signature(code: str) -> list[tuple[str, str, str]]:
    """提取每句教学口播与绑定公式；运行期技术修复不得擅自改写教学语言或删除 cue。"""
    cues = [cue for sc in extract_scenes(code) for cue in sc.cues]
    return [(c.cue_id, c.text, c.math) for c in cues]


def validate_runtime_repair_preservation(
    previous: dict[str, str],
    merged: list[tuple[str, str]],
    error_text: str,
) -> str | None:
    """校验运行期修复只解决技术报错，不重写无关场景或篡改原有题干/推导/口播。"""
    repaired_map = dict(merged)
    loci_scenes = {
        s for s in _SCENE_NAME_RE.findall(error_text) if s in previous
    }
    if loci_scenes:
        touched_unrelated = [
            name for name in previous
            if name not in loci_scenes and repaired_map.get(name) != previous.get(name)
        ]
        if touched_unrelated:
            return (
                "RUNTIME_REPAIR_SCOPE_EXCEEDED: 技术错误仅发生在 "
                + ",".join(sorted(loci_scenes))
                + f"，禁止顺带改写无关场景 {','.join(touched_unrelated)}"
            )

    allows_caption_edit = any(
        prefix in error_text for prefix in ("CAPTION_MATH_NEEDS_REVIEWED_BREAK", "CAPTION_LINE_TOO_LONG", "CAPTION_SAFE_REGION_TOO_SMALL")
    )
    allows_timing_trim = any(
        prefix in error_text for prefix in ("SCENE_ACTION_AFTER_LAST_CUE", "SCENE_ACTION_OVERRUN_AUDIO")
    )
    for name, old_code in previous.items():
        new_code = repaired_map.get(name, "")
        if new_code == old_code:
            continue
        try:
            old_cues = _cues_signature(old_code)
            new_cues = _cues_signature(new_code)
        except Exception:
            continue
        if [c[0] for c in old_cues] != [c[0] for c in new_cues]:
            return (
                f"RUNTIME_REPAIR_SCOPE_EXCEEDED: {name} 擅自增删或重排了 cue_id"
                "（运行修复不得重构教学分段）"
            )
        if not allows_caption_edit and not allows_timing_trim:
            for (cid, old_t, old_m), (_cid2, new_t, new_m) in zip(old_cues, new_cues):
                if old_t != new_t or old_m != new_m:
                    return (
                        f"RUNTIME_REPAIR_SCOPE_EXCEEDED: {name} 的 {cid} 擅自改写了口播或字幕内容"
                        "（技术修复只能修报错语句）"
                    )
        # 防止把整个场景教学推导推倒重写：要求单场景源码行级相似度保留合理下限（极短模板场景除外）
        old_lines = old_code.splitlines()
        new_lines = new_code.splitlines()
        if len(old_lines) >= 12:
            ratio = SequenceMatcher(None, old_lines, new_lines).ratio()
            if ratio < 0.45:
                return (
                    f"RUNTIME_REPAIR_SCOPE_EXCEEDED: {name} 改动幅度过大（相似度 {ratio:.2f}），"
                    "请只最小修改报错代码行，保留原有推导结构"
                )
    return None


def repair_rendered_lesson(
    *,
    source: LessonSource,
    current: Path,
    attempts: Path,
    client,
    fps: int,
    original_error: Exception,
    render_candidate: Callable[[Path], dict],
    watermark_style: dict | None = None,
    images: tuple[str, ...] = (),
    log=None,
    cancel_check=None,
) -> tuple[Path, dict]:
    """在候选目录连续执行：AI修复→静态/公式编译→真实渲染。

    返回真正渲染成功的 (源代码文件夹, 媒体报告)。
    render_candidate 调用者使用完整音轨/字幕/画面参数。
    """
    current = Path(current)
    original_contract = SceneContract.read(current / "scene_contract.json")
    previous = read_scene_sources(current, original_contract)
    if not previous:
        raise RuntimeError("RUNTIME_REPAIR_SOURCE_MISSING")
    last_error = _diagnostic(current, original_error)
    known = set()
    for round_index in range(1, MAX_RUNTIME_REPAIRS + 1):
        if cancel_check:
            cancel_check()
        if log:
            log("运行修复", f"真实 Manim 渲染报错，AI 定向修复第 {round_index}/{MAX_RUNTIME_REPAIRS} 轮")
        signature = (last_error[:1200], tuple(previous.items()))
        if signature in known:
            break
        known.add(signature)
        loci = _extract_repair_loci(last_error, previous)
        response = invoke_scene_model(
            client, system=(prompt_bundle.JOB_RULES_PROVIDER().get('repair_system') or entry('manim_repair.md')+SEP+shared_specs()),
            user_json=_repair_prompt(
                source, ["RUNTIME_RENDER_ERROR: " + last_error[:14000]],
                previous, fps=fps, watermark_style=watermark_style,
                repair_loci=loci,
            ),
            timeout=1800, images=list(images) or None,
        )
        blocks = extract_blocks(response.text)
        if not blocks:
            last_error = "RUNTIME_REPAIR_NO_CODE"
            continue
        # 运行错误恢复只能修现有源码，不能重新生成/删除整幕，
        # 也不能把无标题代码错套到多幕课程的第一幕。
        titles = [name for name, _code in blocks]
        if (len(titles) != len(set(titles))
                or any(name and name not in previous for name in titles)
                or (len(previous) > 1 and any(not name for name in titles))):
            last_error = "RUNTIME_REPAIR_UNAUTHORIZED_SCENE_CHANGE"
            continue
        merged = _merge(previous, blocks)
        if tuple(name for name, _code in merged) != tuple(previous):
            last_error = "RUNTIME_REPAIR_SCENE_ORDER_CHANGED"
            continue
        scope_error = validate_runtime_repair_preservation(previous, merged, last_error)
        if scope_error:
            last_error = scope_error
            continue
        candidate = attempts / f"round_{round_index}"
        try:
            generated = write_scenes(
                merged, candidate / "scenes",
                question=source.problem, reference_solution=source.reference_solution)
            built = build_contract(
                generated, question=source.problem, fps=fps,
                extra_meta=dict(original_contract.meta),
            )
            built.write(candidate / "scene_contract.json")
            if cancel_check:
                cancel_check()
            result = render_candidate(candidate)
            if log:
                log("运行修复", f"第 {round_index} 轮通过真实渲染")
            return candidate, result
        except SceneCodeRejected as exc:
            last_error = "; ".join(exc.errors[:8])
        except EngineError as exc:
            last_error = _diagnostic(candidate, exc)
            import shutil
            shutil.rmtree(candidate / "work", ignore_errors=True)
            if not repairable_render_error(exc):
                raise
            previous = {
                name: code for name, code in merged
            }
    raise RuntimeError(
        "RUNTIME_REPAIR_EXHAUSTED: 真实渲染自动修复失败；"
        + last_error[:450]
    )


__all__ = [
    "MAX_RUNTIME_REPAIRS", "repairable_render_error", "repair_rendered_lesson",
    "validate_runtime_repair_preservation",
]
