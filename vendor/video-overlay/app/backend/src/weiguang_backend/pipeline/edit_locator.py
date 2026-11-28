"""凭原始指令、场景契约和源码定位微调目标。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from animation_engine.code.scene_contract import SceneContract
from .scene_model_call import invoke_scene_model

_CN = {"一":1, "二":2, "三":3, "四":4, "五":5, "六":6, "七":7,
       "八":8, "九":9, "十":10}
SCENE_NUMBER = r"[一二三四五六七八九十\d]{1,3}"
_SCOPED_SCENE = re.compile(rf"^(?:只)?(?:把|改|修改|调整|在)?第({SCENE_NUMBER})幕(?:的|中|里|上|内)")
_COMPLEX_SCOPE = re.compile(
    rf"从|第{SCENE_NUMBER}幕|之后|以后|之前|以前|起|除外|以外|之外|以及|同时|其他|其余|每一幕|整节课|全课|全篇|全程"
)
_LOCATOR_SYSTEM = """
你是 Manim 教学视频源码的只读精确定位器。必须结合用户原话、完整场景代码和口播目录，
输出严格 JSON：{"scenes":["scene_01","scene_03"]}。只允许现有文件名，不解释。
1. 用户未限定位置：找到所有与修改要求匹配的场景（变量、文字、发音、板书、
   数学图形、字幕、场景切换等），不能只返回最相关的一个。
2. 用户明确限定某幕、某一段、某个图形时：只选择含该对象的具体场景，
   不能扩展到别的场景。跨幕或起止区间应包含区间内所有匹配场景。
   “从第二幕开始”含第二幕和后续各幕；“除第二幕外”排除第二幕。
3. 不要根据“第几幕”猜文件名；以下 catalogue 已列出真实对应关系。
4. 不存在任何符合条件的目标时返回空列表，不能为了交差虚构目标。
5. 发音更正只定位原音轨中读错的语境，其他同字但读音不同的位置不可更改。
6. 用户明确要求新增一幕但新幕尚不存在时，返回应当承接内容、
   需要被参考的相邻旧幕作为锚点；分幕时返回要拆开的原有幕；
   合幕时返回所有参与合并的原有幕，不可因之后会删除其中一幕而省略。
只执行只读定位，不能改写任何代码。
"""

@dataclass(frozen=True)
class EditTargets:
    scenes: tuple[str, ...]
    reasons: tuple[str, ...]


def scene_ordinal(raw: str) -> int | None:
    if raw.isdigit():
        return int(raw) or None
    if raw in _CN:
        return _CN[raw]
    if "十" in raw and raw.count("十") == 1:
        tens, units = raw.split("十")
        if (not tens or tens in _CN) and (not units or units in _CN):
            return _CN.get(tens, 1) * 10 + _CN.get(units, 0)
    return None


def locate_scenes(tasks: tuple[str, ...], contract: SceneContract,
                  sources: dict[str, str], client=None,
                  *, structure_action: str = "none",
                  original_instruction: str = "",
                  source_modified: bool = False,
                  previous_question: str = "",
                  reference_solution: str = "") -> EditTargets:
    if not sources:
        raise ValueError("EDIT_NO_SCENE_SOURCES")
    scene_files = [Path(scene.path).stem for scene in contract.scenes]
    order = list(dict.fromkeys((*scene_files, *sources)))
    # Explicit out-of-range scene references must never fall back to the only scene.
    if len(sources) == 1 and structure_action == "none" and not any(_COMPLEX_SCOPE.search(t) for t in tasks):
        only_scene = next(iter(sources))
        return EditTargets((only_scene,), (f"单幕课程直达定位：{only_scene}",))
    selected: set[str] = set()
    reasons: list[str] = []
    ambiguous: list[str] = []
    for instruction in tasks:
        match = _SCOPED_SCENE.match(instruction.strip())
        if (match and structure_action == "none"
                and not _COMPLEX_SCOPE.search(instruction.strip()[match.end():])):
            ordinal = scene_ordinal(match.group(1))
            if ordinal and ordinal <= len(scene_files):
                target = scene_files[ordinal - 1]
                selected.add(target)
                reasons.append(f"用户限定场景：{target}")
        else:
            # 提到某幕可以表示范围起点、终点或排除项。把完整要求交给 AI。
            ambiguous.append(instruction)

    if ambiguous:
        if client is None:
            raise ValueError("EDIT_AI_CONFIGURATION_REQUIRED")
        catalogue = [
            {"number": number, "scene": item.scene_id, "file": Path(item.path).stem,
             "cues": [
                 {"id": cue.cue_id, "kind": cue.method,
                  "text": cue.text, "math": cue.math}
                 for cue in contract.cues if cue.scene_id == item.scene_id
             ]}
            for number, item in enumerate(contract.scenes, start=1)
        ]
        # 未限定范围时必须读到每个场景源码，截断会漏掉靠后的目标。
        total_chars = sum(len(code) for code in sources.values())
        if total_chars > 600000:
            raise ValueError("EDIT_SCENE_SOURCES_TOO_LARGE_TO_LOCATE_SAFELY")
        payload_obj = {
            "tasks": ambiguous, "original_instruction": original_instruction or "；".join(tasks),
            "catalogue": catalogue, "sources": sources,
            "already_selected": list(selected),
            "structure_action": structure_action,
        }
        if source_modified:
            payload_obj["source_modified"] = True
            payload_obj["latest_question"] = contract.question[:3000]
            if previous_question:
                payload_obj["previous_question"] = previous_question[:3000]
            if reference_solution:
                payload_obj["latest_reference_solution"] = reference_solution[:6000]
        payload = json.dumps(payload_obj, ensure_ascii=False)
        try:
            response = invoke_scene_model(
                client, system=_LOCATOR_SYSTEM, user_json=payload, timeout=180,
            )
            answer = response.text
            match = re.search(r"\{[\s\S]*\}", answer)
            parsed = json.loads(match.group() if match else answer)
        except (ValueError, TypeError, RuntimeError, TimeoutError) as exc:
            raise ValueError("EDIT_SCENE_LOCATION_MODEL_FAILED") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("scenes"), list):
            raise ValueError("EDIT_SCENE_LOCATION_INVALID_RESPONSE")
        names = parsed["scenes"]
        if any(not isinstance(name, str) or name not in sources for name in names):
            raise ValueError("EDIT_SCENE_LOCATION_INVALID_TARGET")
        selected.update(names)
        reasons.append("AI 读取全部场景后定位：" + ", ".join(names))

    if not selected:
        if structure_action == "insert" and order:
            # 原视频还没有新幕，不可能定位到新幕自身；
            # 给编辑模型一个相邻锚点，不授权扩散修改其他旧场景。
            return EditTargets((order[0],), ("新幕尚未存在，以开头旧幕作为参考锚点",))
        # 普通微调真实无匹配：不允许扩大成“编辑全课”。
        return EditTargets((), tuple(reasons or ("未找到与用户要求匹配的场景",)))

    return EditTargets(tuple(name for name in order if name in selected),
                       tuple(reasons))


__all__ = ["EditTargets", "locate_scenes", "scene_ordinal"]
