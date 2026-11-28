"""Deterministic example selection; no extra AI call or chat context."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "ai" / "prompts"
SHARED = ["01_teacher_role.md","02_opening_reading.md","03_thinking_guidance.md","04_knowledge.md","05_derivation.md","06_common_errors.md","07_math_writing.md","08_math_visualization.md","09_layout_transition.md","10_speech.md","11_caption_sync.md","12_summary.md","13_manim_technical.md"]
COMMON = [name for name in SHARED if name not in {"02_opening_reading.md", "04_knowledge.md", "12_summary.md"}]
LIMIT = 120000
# Reserve adapter supplement budget (32 KB) and bridge framing.
RESERVE = 34000
SEP = "\n\n---\n\n"
# Adapter binds this to the immutable DB snapshot for the current job.
JOB_RULES_PROVIDER = lambda: {}

def shared_specs(business="question"):
    if business not in {"question", "knowledge"}:
        raise ValueError("UNKNOWN_VIDEO_BUSINESS")
    files = SHARED if business == "question" else COMMON
    shared = SEP.join((PROMPTS_DIR / "shared" / name).read_text(encoding="utf-8").strip() for name in files)
    return shared + SEP + entry("question/scope.md") if business == "question" else shared

def knowledge_rules(teaching_type):
    common = entry("knowledge/common.md")
    if teaching_type in {"with_proof", "without_proof"}:
        return common + SEP + entry("knowledge/" + teaching_type + ".md")
    if teaching_type == "auto":
        return SEP.join([common, "以下两种专项互斥：仅当原文含实际证明或推导时选择含证明，否则选择无证明；证明略、概念说明、例题解析不属于证明。", entry("knowledge/with_proof.md"), entry("knowledge/without_proof.md")])
    raise ValueError("UNKNOWN_KNOWLEDGE_TEACHING_TYPE")

def entry(name):
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()

def ensure_budget(system, user):
    if len(system.encode("utf-8")) + len(user.encode("utf-8")) + RESERVE > LIMIT:
        raise RuntimeError("VIDEO_PROMPT_BUDGET_EXCEEDED: 题源与必要规范超过视频提示词预算，不截断")

def choose_examples(meta, problem, solution, system, user, *, business='question', teaching_type='auto'):
    ensure_budget(system, user)
    folder = PROMPTS_DIR / "examples"
    if not (folder / "index.json").is_file():
        return system, []
    records = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    structured = json.dumps(meta or {}, ensure_ascii=False).casefold()
    body = (problem + "\n" + solution).casefold()
    ranked = []
    for rec in records:
        scope = rec.get("scope", "question" if rec["kind"] == "complete" else "shared")
        if business == "question" and scope != "question" and scope != "shared":
            continue
        if business == "knowledge":
            if scope == "question" or rec["id"] in {"B01", "B02", "B03", "B04", "B15", "B16", "B17", "B18"}:
                continue
            if scope in {"with_proof", "without_proof"} and teaching_type != scope:
                continue
        score = sum(4 * (k.casefold() in structured) + (k.casefold() in body) for k in rec["keywords"])
        if score:
            ranked.append((-score, rec["id"], rec))
    counts = {"complete": 0, "teaching": 0, "technical": 0}
    limits = {"complete": 1, "teaching": 3, "technical": 2}
    selected = []
    for _, _, rec in sorted(ranked, key=lambda x: (x[0], x[1])):
        kind = rec["kind"]
        if counts[kind] >= limits[kind]:
            continue
        path = (folder / rec["path"]).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():
            continue
        content = path.read_text(encoding="utf-8").strip()
        candidate = system + SEP + "参考示例 " + rec["id"] + "（非固定模板）\n" + content
        if len(candidate.encode("utf-8")) + len(user.encode("utf-8")) + RESERVE > LIMIT:
            continue
        system = candidate
        counts[kind] += 1
        selected.append({"id": rec["id"], "sha256": hashlib.sha256(content.encode()).hexdigest()})
    return system, selected

def capture_rules(meta, problem, solution, user):
    """Read all necessary rule text once, before the job is committed."""
    context = (meta or {}).get("source_context") or {}
    business = context.get("business_type", "question")
    shared = shared_specs(business)
    if business == "knowledge":
        teaching_type = context.get("teaching_type", "auto")
        scoped = knowledge_rules(teaching_type)
        fixed = SEP.join([entry("manim_knowledge_teacher.md"), shared, scoped])
        # Existing complete example classroom and question-only teaching references
        # must not be injected into a knowledge lesson as a full-course template.
        system, selected = choose_examples(meta, problem, solution, fixed, user, business="knowledge", teaching_type=teaching_type)
        repair = SEP.join([entry("manim_repair.md"), shared, scoped, "题源字段指可信知识单元、证明及已关联例题；不改变其数学内容或教学类型。"])
        editor = SEP.join([entry("manim_editor.md"), shared, scoped, "当前课程主体为知识单元；仅按明确指令修改对应知识解释、证明、例题及必要衔接。"])
        return {"version":"v1", "business_type":business, "teaching_type":teaching_type, "shared_sha256":hashlib.sha256(shared.encode()).hexdigest(), "scope_sha256":hashlib.sha256(scoped.encode()).hexdigest(), "examples":selected, "system":system, "repair_system":repair, "editor_system":editor}
    fixed = entry("manim_teacher.md") + SEP + shared
    system, selected = choose_examples(meta, problem, solution, fixed, user)
    return {"version":"v1", "business_type":"question", "shared_sha256":hashlib.sha256(shared.encode()).hexdigest(),
            "examples":selected, "system":system,
            "repair_system":entry("manim_repair.md") + SEP + shared,
            "editor_system":entry("manim_editor.md") + SEP + shared}

def snapshot(source, user, output_dir):
    pinned = JOB_RULES_PROVIDER() or capture_rules(
        source.question_meta, source.problem, source.reference_solution, user)
    system = pinned["system"]
    ensure_budget(system, user)
    data = {**pinned, "source_sha256":source.source_sha256, "user_json":user}
    target = Path(output_dir) / "prompt_snapshot.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return system

def repair_system(output_dir, user):
    target = Path(output_dir) / "prompt_snapshot.json"
    system = json.loads(target.read_text(encoding="utf-8"))["repair_system"]
    ensure_budget(system, user)
    return system


def editor_rules():
    pinned = JOB_RULES_PROVIDER()
    if pinned:
        system = pinned["editor_system"]
        inherited = pinned.get("inherited_supplement", "")
        if inherited:
            system += SEP + "原课已采用的用户教学要求（只用于维持未涉及内容；当前明确微调指令优先，不据此扩大修改范围）：\n" + inherited
        return system
    return entry("manim_editor.md") + SEP + shared_specs()
