"""Deterministic example selection; no extra AI call or chat context."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "ai" / "prompts"
SHARED = ["01_teacher_role.md","02_opening_reading.md","03_thinking_guidance.md","04_knowledge.md","05_derivation.md","06_common_errors.md","07_math_writing.md","08_math_visualization.md","09_layout_transition.md","10_speech.md","11_caption_sync.md","12_summary.md","13_manim_technical.md"]
LIMIT = 120000
# Reserve adapter supplement budget (32 KB) and bridge framing.
RESERVE = 34000
SEP = "\n\n---\n\n"

def shared_specs():
    return SEP.join((PROMPTS_DIR / "shared" / name).read_text(encoding="utf-8").strip() for name in SHARED)

def entry(name):
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()

def ensure_budget(system, user):
    if len(system.encode("utf-8")) + len(user.encode("utf-8")) + RESERVE > LIMIT:
        raise RuntimeError("VIDEO_PROMPT_BUDGET_EXCEEDED: 题源与必要规范超过视频提示词预算，不截断")

def choose_examples(meta, problem, solution, system, user):
    ensure_budget(system, user)
    folder = PROMPTS_DIR / "examples"
    if not (folder / "index.json").is_file():
        return system, []
    records = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    structured = json.dumps(meta or {}, ensure_ascii=False).casefold()
    body = (problem + "\n" + solution).casefold()
    ranked = []
    for rec in records:
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

def snapshot(source, user, output_dir):
    shared = shared_specs()
    fixed = entry("manim_teacher.md") + SEP + shared
    system, selected = choose_examples(source.question_meta, source.problem, source.reference_solution, fixed, user)
    repair = entry("manim_repair.md") + SEP + shared
    data = {"version":"v1", "shared_sha256":hashlib.sha256(shared.encode()).hexdigest(),
            "source_sha256":source.source_sha256, "examples":selected, "system":system,
            "repair_system":repair}
    target = Path(output_dir) / "prompt_snapshot.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return system

def repair_system(output_dir, user):
    target = Path(output_dir) / "prompt_snapshot.json"
    system = json.loads(target.read_text(encoding="utf-8"))["repair_system"]
    ensure_budget(system, user)
    return system
