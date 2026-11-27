"""Derived question filter facts; never change original text or answer."""
from app.core.question_structure import resolve
from app.core.question_matching import method_names

def filter_facts(content,answer,solution,question_type,stored=None):
    result={"answer_complete":bool((answer or "").strip()),"solution_complete":bool((solution or "").strip()),"multi":False,"single":False,"ambiguous":False}
    try:
        data=resolve(content,answer,solution,question_type,stored)
        groups=[p.methods for p in data.subquestions] if data.subquestions else [data.methods]
        counts=[sum(bool(m.body.strip()) for m in g) for g in groups]
        result["ambiguous"]=bool(data.warnings)
        if data.subquestions:result["answer_complete"]=all(bool(p.answer.strip()) for p in data.subquestions)
        if data.blanks:result["answer_complete"]=all(bool(p.answer.strip()) for p in data.blanks)
        if data.options:result["answer_complete"]=bool(data.correct_options)
        result["solution_complete"]=bool(counts) and all(n>0 for n in counts)
        result["multi"]=any(n>1 for n in counts) and not data.warnings
        result["single"]=bool(counts) and all(n==1 for n in counts) and not data.warnings
    except (ValueError,TypeError):
        result["ambiguous"]=True
    if result["ambiguous"]:
        result["answer_complete"]=False
        result["solution_complete"]=False
    for name in method_names(solution):result["method:"+name]=True
    return result
