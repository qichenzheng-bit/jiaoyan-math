"""局部 Manim 编辑：只向 AI 发送目标场景；只允许合并已授权的文件。"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from animation_engine.code.scene_contract import SceneContract
from animation_engine.render.layout_constraints import layout_prompt_fields
from animation_engine.speech.voice_rules import pronounce_for_tts
from .scene_codegen import extract_blocks, load_shared_prompt_specs
from .prompt_bundle import editor_rules

EDITOR_PROMPT = Path(__file__).resolve().parent.parent / "ai" / "prompts" / "manim_editor.md"


class EditOutputError(ValueError):
    pass


def editor_system_prompt() -> str:
    return editor_rules()


def manifest_layout_warnings(manifest: dict | None,
                             target_scene_ids: set[str] | tuple[str, ...] = ()
                             ) -> list[dict]:
    """从上一版 manifest 提取实测布局碰撞告警，帮助微调准确避让。"""
    if not isinstance(manifest, dict):
        return []
    scenes = manifest.get("scenes") or ()
    targets = set(target_scene_ids)
    collected: list[dict] = []
    for item in scenes:
        if not isinstance(item, dict):
            continue
        scene_id = str(item.get("scene_id") or "")
        if targets and scene_id and scene_id not in targets:
            continue
        for warning in item.get("layout_warnings") or ():
            if not isinstance(warning, dict):
                continue
            collected.append({"scene": scene_id, **warning})
            if len(collected) >= 24:
                return collected
    return collected


def edit_payload(tasks: tuple[str, ...], contract: SceneContract,
                 current: dict[str, str], target_files: tuple[str, ...],
                 *, reference_solution: str = "", answer: str = "",
                 previous_question: str = "", source_modified: bool = False,
                 errors: str = "",
                 reference_images: tuple[str, ...] = (),
                 watermark_style: dict | None = None,
                 voice_rules: dict | None = None, instruction: str = "",
                 allow_new: bool = False,
                 previous_layout_warnings: list[dict] | None = None,
                 voice_only: bool = False) -> str:
    index = [
        {"id": cue.cue_id, "scene": cue.scene_id, "method": cue.method,
         "text": cue.text[:150], "math": cue.math[:150]}
        for cue in contract.cues
    ]
    target_scene_ids = {scene.scene_id for scene in contract.scenes
                        if Path(scene.path).stem in target_files}
    payload = {
        "exact_instructions": list(tasks),
        "original_instruction": instruction or "；".join(tasks),
        "target_files": list(target_files),
        "allow_new_scenes": allow_new,
        "current_tts_text": {
            cue.cue_id: cue.tts_text or pronounce_for_tts(cue.text, voice_rules)
            for cue in contract.cues if cue.scene_id in target_scene_ids
        },
        "current_target_code": {name: current[name] for name in target_files},
        "course_cue_index": index,
        "question": contract.question,
        "reference_solution": reference_solution,
        "answer": answer,
        "previous_validation_errors": errors,
        "fps": contract.fps,
        **layout_prompt_fields(watermark_style),
        "requirements": [
            "只修改所需场景；别的场景由程序原样保留",
            "输出每个修改场景完整代码，不输出不相关文件",
            "数学条件结论与口播时间轴不可意外更改",
            "未要求改动的原有正确推导、开场白和公式尽量保留；若用户明确要求改开场、去啰嗦或补充图像，直接按要求落实",
            "新口播 ID 必须全课唯一",
            "`allow_new_scenes` 为 true 时才可返回新的 scene_NN 代码块；要求删除某一幕时，不要返回该幕代码",
            "允许在 AuthoredScene 场景源码中按要求修改对象位置、字号、动画与切幕，保持其余逻辑不变",
        ],
    }
    from .source_assets import knowledge_envelope
    unit=knowledge_envelope(reference_solution)
    if unit is not None:
        payload["business_type"]="knowledge"
        payload["knowledge_unit"]=unit
        payload["teaching_type"]=contract.meta.get("knowledge_teaching_type",unit["teaching_type"])
        for field in ("question","reference_solution","answer"):
            payload.pop(field,None)
        payload["requirements"].append("知识单元及题库关联关系是可信原始资料；存在关联题时只允许从原有关联题选择1～2道，不得改写其题干、答案或解析；无关联题才允许新设计例题。不得改动原始证明或将无证明课变成正式证明课。")
    if voice_only:
        payload["voice_only"] = True
        payload["requirements"] = [
            "本次只修正读音：只允许新增或修改 start_cue 的 tts_text 关键字参数",
            "严禁改动 spoken_text（第二参数）、caption_math、板书、公式、图形、"
            "动画、切幕、字号、位置、颜色",
            "严禁新增、删除或重排场景文件，严禁改类名、cue_id 与函数结构",
            "没有需要修正读音的 cue 就原样返回代码",
        ]
    if source_modified:
        payload["source_modified"] = True
        if previous_question:
            payload["previous_question"] = previous_question
        payload["requirements"].append(
            "题库原题已更新：若用户指令涉及同步/修改题干、条件、解析或结论，必须以当前输入的最新 question、reference_solution 和 answer 为准更新板书、公式与口播")
    if previous_layout_warnings:
        payload["previous_layout_warnings"] = list(previous_layout_warnings)[:24]
    if reference_images:
        # 图片按这顺序随消息一起发送；这里只用来告诉模型它们是什么
        payload["reference_images"] = [Path(p).name for p in reference_images]
        payload["requirements"].append(
            "参考图片是视觉参考，用来判断版式、颜色、标注位置，不要直接复刻图片内容")
    return json.dumps(payload, ensure_ascii=False)


_NEW_SCENE = re.compile(r"scene_\d{2,3}")


def _narrated_classes(source: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise EditOutputError(f"EDIT_SOURCE_SYNTAX: {exc.msg}") from exc
    result = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [getattr(base, "id", getattr(base, "attr", ""))
                     for base in node.bases]
            if "AuthoredScene" in bases:
                result.append(node.name)
    return tuple(result)


def merge_targeted_sources(current: dict[str, str], output: str,
                           targets: tuple[str, ...], *,
                           allow_new: bool = False,
                           ) -> tuple[dict[str, str], tuple[str, ...]]:
    """不接受无场景、越界写入、重复同名代码块、无实际改变等假成功。"""
    if targets and not set(targets).issubset(current):
        raise EditOutputError("EDIT_TARGETS_INVALID")
    blocks = extract_blocks(output)
    if not blocks:
        raise EditOutputError("EDIT_RESPONSE_NO_CODE")
    if len(blocks) == 1 and not blocks[0][0]:
        if len(targets) != 1:
            raise EditOutputError("EDIT_MULTISCENE_TITLES_REQUIRED")
        blocks = [(targets[0], blocks[0][1])]
    if any(not name for name, _ in blocks):
        raise EditOutputError("EDIT_RESPONSE_MISSING_TITLE")
    names = [name for name, _ in blocks]
    if len(names) != len(set(names)):
        raise EditOutputError("EDIT_DUPLICATE_SCENE_OUTPUT")
    new_names = [name for name in names if name not in current]
    if new_names and (
        not allow_new or any(not _NEW_SCENE.fullmatch(name) for name in new_names)
    ):
        raise EditOutputError("EDIT_OUT_OF_SCOPE_SCENE: " + ", ".join(new_names))
    updated = dict(current)
    changed: list[str] = []
    for name, code in blocks:
        normalized = code.rstrip() + "\n"
        if not normalized.strip() or "AuthoredScene" not in normalized:
            raise EditOutputError("EDIT_SCENE_NOT_COMPLETE: " + name)
        if name not in current:
            # 用户要求新增/拆分场景：新文件必须自带 AuthoredScene 子类
            if not _narrated_classes(normalized):
                raise EditOutputError("EDIT_SCENE_CLASS_MISSING: " + name)
            updated[name] = normalized
            changed.append(name)
            continue
        if name not in targets:
            raise EditOutputError("EDIT_OUT_OF_SCOPE_SCENE: " + name)
        if (_narrated_classes(normalized) != _narrated_classes(current[name])
                or not _narrated_classes(normalized)):
            raise EditOutputError("EDIT_SCENE_CLASS_CHANGED: " + name)
        if normalized != current[name].rstrip() + "\n":
            # 不把仅重排空格、换行、注释等无实质代码变化判成成功微调。
            original_ast = ast.dump(ast.parse(current[name]), include_attributes=False)
            edited_ast = ast.dump(ast.parse(normalized), include_attributes=False)
            if original_ast != edited_ast:
                updated[name] = normalized
                changed.append(name)
    # 没有实质改动不算失败：上层按"未修改"处理（不渲染、不报错）。
    return updated, tuple(changed)


_EFFECT_REVIEW_SYSTEM = """
你只检查用户的自然语言代码微调是否被准确执行；不审查数学正确性、讲法质量或美观程度。
输入含原始指令、允许编辑的文件、修改前后全部源码。
只输出 JSON：{"applied":true,"unrelated_changed":false,"missing":[],"unexpected":[]}。
判断标准：
- 用户未限定范围：所有实际符合指令的匹配处都已修改，包含必要关联口播、字幕、板书和标签；
- 用户限定某个位置：只能更改该位置及其必须联动的对象，其他相同字母/汉字/公式不能被误改；
- 发音要求只影响匹配读音的句子，不应影响同字的其他读法，也不必改屏显汉字；
- 无关场景不得改变，必要联动的结构/导入修改除外；
- 只根据明确的原始指令和源码差异判断，不能补充或评分数学、教学质量。
存在遗漏则 applied=false 并在 missing 写出定位依据；无关改动则 unrelated_changed=true
并在 unexpected 写出内容。无法验证时 applied=false，说明需要补充的依据。
"""


def verify_edit_instruction_with_ai(
    client, tasks: tuple[str, ...], before: dict[str, str],
    after: dict[str, str], targets: tuple[str, ...], *, instruction: str = "",
    question: str = "", reference_solution: str = "",
    source_modified: bool = False,
) -> None:
    """验证用户目标和实际代码变化；不把数学/教学评分当作技术验收。"""
    from .scene_model_call import invoke_scene_model
    payload_obj = {
        "tasks": list(tasks),
        "original_instruction": instruction or "；".join(tasks),
        "authorized_scenes": list(targets),
        # 核验时检查全课代码，不能只看 locator 已选的幕；
        # 否则未指定范围时漏改的其他幕永远无法被发现。
        "source_before": before,
        "source_after": after,
        "new_scenes": {name: code for name, code in after.items() if name not in before},
    }
    if source_modified:
        payload_obj["source_modified"] = True
        if question:
            payload_obj["latest_question"] = question[:3000]
        if reference_solution:
            payload_obj["latest_reference_solution"] = reference_solution[:6000]
    payload = json.dumps(payload_obj, ensure_ascii=False)
    if len(payload) > 650000:
        raise EditOutputError("EDIT_EFFECT_REVIEW_INPUT_TOO_LARGE")
    try:
        response = invoke_scene_model(
            client, system=_EFFECT_REVIEW_SYSTEM, user_json=payload, timeout=180)
        match = re.search(r"\{[\s\S]*\}", response.text)
        data = json.loads(match.group() if match else response.text)
    except (ValueError, TypeError, RuntimeError, TimeoutError) as exc:
        raise EditOutputError("EDIT_EFFECT_REVIEW_INVALID_JSON") from exc
    if (not isinstance(data, dict)
            or type(data.get("applied")) is not bool
            or type(data.get("unrelated_changed")) is not bool):
        raise EditOutputError("EDIT_EFFECT_REVIEW_INVALID_RESPONSE")
    if not data["applied"] or data["unrelated_changed"]:
        details = json.dumps({
            "missing": data.get("missing", []),
            "unexpected": data.get("unexpected", []),
        }, ensure_ascii=False)
        raise EditOutputError("EDIT_INSTRUCTION_NOT_FULLY_APPLIED: " + details[:1200])


def _strip_tts_text(tree: ast.AST) -> str:
    """去掉所有 start_cue 的 tts_text 参数后再序列化，用于"只改读音"判定。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else "")
        if name == "start_cue":
            node.keywords = [kw for kw in node.keywords if kw.arg != "tts_text"]
    return ast.dump(tree, include_attributes=False)


def assert_only_tts_text_changed(previous: dict[str, str],
                                 updated: dict[str, str]) -> None:
    """仅读音修正的硬约束：除 tts_text 外任何源码变化都拒绝。

    读音是 TTS 的事，板书、字幕、动画一行都不该动。这里用 AST 对比：
    - 去掉 tts_text 后结构不同 → 说明改了别的东西，拒绝；
    - 连 tts_text 都没变（只改注释/格式）→ 要求模型重新给有效改动。
    """
    if set(updated) - set(previous):
        raise EditOutputError("EDIT_VOICE_ONLY_NEW_SCENE")
    if tuple(previous) != tuple(updated):
        raise EditOutputError("EDIT_VOICE_ONLY_SCENE_SET_CHANGED")
    changed_tts = False
    for name, code in updated.items():
        old = previous.get(name)
        if old is None:
            raise EditOutputError("EDIT_VOICE_ONLY_NEW_SCENE")
        try:
            full_before = ast.dump(ast.parse(old), include_attributes=False)
            full_after = ast.dump(ast.parse(code), include_attributes=False)
            stripped_before = _strip_tts_text(ast.parse(old))
            stripped_after = _strip_tts_text(ast.parse(code))
        except SyntaxError as exc:
            raise EditOutputError(f"EDIT_SOURCE_SYNTAX: {exc.msg}") from exc
        if stripped_before != stripped_after:
            raise EditOutputError("EDIT_VOICE_ONLY_VIOLATION")
        if full_before != full_after:
            changed_tts = True
    if not changed_tts:
        raise EditOutputError("EDIT_VOICE_ONLY_NO_TTS_CHANGE")


def validate_edit_scope_ast(before: dict[str, str], after: dict[str, str], *,
                            targets: tuple[str, ...],
                            allow_new: bool = False,
                            allowed_removed: tuple[str, ...] = ()) -> None:
    """AST 级微调范围守卫：确保未授权场景一字未改、未发生无意义结构偏移。"""
    target_set = set(targets)
    for name, old_code in before.items():
        if name not in after:
            if name not in allowed_removed:
                raise EditOutputError("EDIT_UNAUTHORIZED_REMOVAL: " + name)
            continue
        new_code = after[name]
        if new_code == old_code:
            continue
        if name not in target_set:
            raise EditOutputError("EDIT_OUT_OF_SCOPE_SCENE: " + name)
    for name in after:
        if name not in before and not allow_new:
            raise EditOutputError("EDIT_OUT_OF_SCOPE_SCENE: " + name)


__all__ = ["EditOutputError", "editor_system_prompt", "edit_payload",
           "manifest_layout_warnings", "merge_targeted_sources",
           "verify_edit_instruction_with_ai", "assert_only_tts_text_changed",
           "validate_edit_scope_ast"]
