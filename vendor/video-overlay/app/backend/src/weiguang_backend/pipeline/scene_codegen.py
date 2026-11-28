"""场景代码生成 · 让 AI 直接写 Manim

职责：
    读固定教学规范 → 调用当前任务选定的模型 → 拿到 Manim 源码 → 静态校验 →
    按场景落盘 → 组装场景契约。

不做：
    不生成 LessonPlan / LessonIR / 教学包 / 分镜。代码就是唯一产物。
"""
from __future__ import annotations

from pathlib import Path
import json

from animation_engine.render.layout_constraints import layout_prompt_fields

from .scene_output import (
    Attempt, GeneratedScenes, SceneCodeRejected, build_contract,
    extract_blocks, scene_file_names, write_scenes,
)
from .scene_model_call import invoke_scene_model, usage_delta, usage_snapshot
from .source_assets import LessonSource

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "ai" / "prompts"
PROMPT_FILE = PROMPTS_DIR / "manim_teacher.md"
from . import prompt_bundle
SHARED_PROMPT_FILES = tuple(prompt_bundle.SHARED)


def load_shared_prompt_specs() -> str:
    """加载生成与微调共用的公共教学、书写、排版、口播与技术规范。"""
    parts: list[str] = []
    shared_dir = PROMPTS_DIR / "shared"
    for name in SHARED_PROMPT_FILES:
        path = shared_dir / name
        if not path.is_file():
            raise RuntimeError(f"SCENE_SHARED_PROMPT_MISSING: {path}")
        parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts)


def system_prompt() -> str:
    """固定教学规范。缺文件直接报错——不要用内置文案顶替。"""
    if not PROMPT_FILE.is_file():
        raise RuntimeError(f"SCENE_PROMPT_MISSING: {PROMPT_FILE}")
    teacher_body = PROMPT_FILE.read_text(encoding="utf-8").strip()
    return teacher_body + "\n\n---\n\n" + load_shared_prompt_specs()




def generate_scene_sources(*, source: LessonSource, client, output_dir: Path,
                           fps: int, log=None, phase=None,
                           expected_scenes: int | None = None,
                           images: tuple[str, ...] = (),
                           watermark_style: dict | None = None) -> GeneratedScenes:
    """第 1 轮生成。校验失败抛 SceneCodeRejected，由修复器接手。"""
    folder = Path(output_dir) / "scenes"
    payload = json.loads(source.prompt_payload(fps=fps))
    payload.update(layout_prompt_fields(watermark_style))
    user = json.dumps(payload, ensure_ascii=False)
    if expected_scenes:
        user += f"\n\n建议场景数量：{expected_scenes}"
    images = tuple(str(p) for p in (images or ()) if str(p))
    if images:
        # 题图只作为视觉参考；绝不在生成后注入或替换任何图元。
        user += (
            f"\n\n已随消息发送 {len(images)} 张题目参考图。"
            "先识别所有必要条件、顶点、标注和几何关系，"
            "再由生成代码使用原生 Manim 对象自行绘制所需画面；"
            "不得杜撰原图没有的量，不得让图像替代数学证明。"
        )

    system = prompt_bundle.snapshot(source, user, output_dir)

    if phase:
        phase("生成 Manim 代码")
    if log:
        log("AI", "开始生成代码"
            + (f"（含 {len(images)} 张参考图）" if images else ""))
    try:
        response = invoke_scene_model(
            client, system=system, user_json=user, timeout=1800,
            images=list(images) or None,
        )
    except Exception:
        if log:
            # 运行日志只写中文：具体错误码与英文原文由失败收尾统一翻译。
            log("生成", "模型调用失败，本次生成中止")
        raise
    text = response.text
    seconds = response.seconds
    tokens = response.tokens

    blocks = extract_blocks(text)
    if not blocks:
        raise SceneCodeRejected(
            [f"[output] SCENE_CODE_NOT_FOUND: 模型没有返回可识别的 Python 代码块"
             f"（收到 {len(text)} 字符）"], {})
    if log:
        log("生成", "生成完毕")

    # 先存草稿：校验没过时，修复轮次仍能看到原代码，而不是从零重写。
    draft = Path(output_dir) / "draft"
    draft.mkdir(parents=True, exist_ok=True)
    for name, (_title, code) in zip(scene_file_names(blocks), blocks):
        (draft / f"{name}.py").write_text(code.rstrip() + "\n", encoding="utf-8")

    generated = write_scenes(
        blocks, folder, question=source.problem,
        reference_solution=source.reference_solution)
    generated.attempts = [Attempt(round=1, ok=True, seconds=seconds,
                                  chars=len(text), tokens=tokens)]
    generated.tokens = tokens
    return generated


__all__ = [
    "Attempt", "GeneratedScenes", "SceneCodeRejected",
    "system_prompt", "extract_blocks",
    "write_scenes", "build_contract", "generate_scene_sources",
    "usage_snapshot", "usage_delta",
]
