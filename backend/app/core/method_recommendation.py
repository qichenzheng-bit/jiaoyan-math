"""Select one complete solution, or one method per independent subquestion.

AI only recommends existing method indices; it never rewrites the mathematics.
"""
from app.core.question_structure import resolve, project, digest
from app.core.solution_methods import recommended_solution

def groups_for(r):
    data=resolve(r.content,r.answer,r.solution,r.question_type,getattr(r,"question_data",None))
    if data.warnings:raise ValueError("小问或选项结构待核对，暂不能自动比较解法")
    groups=[(str(p.number),p.methods) for p in data.subquestions] if data.subquestions else [("main",data.methods)]
    return data,[(key,[m for m in methods if m.body.strip()]) for key,methods in groups]

def choices_for(r):
    data,groups=groups_for(r)
    return [{"key":k,"methods":[{"index":i+1,"name":m.name,"body":m.body,"recommended":m.recommended} for i,m in enumerate(ms)]} for k,ms in groups]

def validate_choices(groups,choices):
    expected={g["key"] for g in groups if g["methods"]}
    if not isinstance(choices,dict) or set(choices)!=expected:raise ValueError("推荐解法必须覆盖所有含解析的小问")
    for g in groups:
        if g["key"] not in expected:continue
        n=choices[g["key"]]
        if type(n) is not int or not 1<=n<=len(g["methods"]):raise ValueError("推荐解法编号无效")
    return choices

def apply_choices(r,choices):
    data,groups=groups_for(r)
    validate_choices(choices_for(r),choices)
    selected={k:[m.model_copy(update={"recommended":i+1==choices.get(k)}) for i,m in enumerate(ms)] for k,ms in groups}
    if data.subquestions:
        data=data.model_copy(update={"subquestions":[p.model_copy(update={"methods":selected[str(p.number)]}) for p in data.subquestions]})
    else:data=data.model_copy(update={"methods":selected["main"]})
    # Never overwrite the original question/answer when changing the selected method.
    solution=project(data)["solution"]
    return solution,data.model_copy(update={"legacy_digest":digest(r.content,r.answer,solution,r.question_type)}).model_dump()

def video_solution(r):
    # Old lightweight objects in bridge tests, and simple legacy single-method questions.
    if not hasattr(r,"question_data"):return recommended_solution(r.solution)
    data,groups=groups_for(r)
    def one(ms):
        m=next((m for m in ms if m.recommended),ms[0] if ms else None)
        if m is None:return ""
        return (m.name+"\n" if m.name else "")+m.body
    if data.subquestions:
        if any(not ms for _,ms in groups):raise ValueError("部分小问缺少推荐解析，请先补齐")
        return "\n".join("("+k+") "+one(ms) for k,ms in groups)
    return one(groups[0][1])
