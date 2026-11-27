"""Shared question-first retrieval. Fingerprints are candidates, not mathematical proofs."""
from difflib import SequenceMatcher
import re
from sqlalchemy import select, or_
from app.models import TeachingResource as Resource, ResourceKnowledgeLink, KnowledgePointCatalog
from app.core.content_normalization import canonical_text, question_stem_key, question_fingerprint, unit_fingerprint
from app.core.solution_methods import parse_methods

# Conservative equality: preserve case, whitespace between TeX command names and arguments,
# superscripts, signs, font semantics, delimiters, option order and every condition.
def strict_text(text):
    return (text or "").replace("\r\n","\n").replace("\r","\n").strip()

def same_question(a,b):
    return bool(strict_text(a) and strict_text(a)==strict_text(b))

def answer_conflict(a,b):
    return bool(a.strip() and b.strip() and strict_text(a)!=strict_text(b))

def method_keys(text):
    return {strict_text(m["body"]) for m in parse_methods(text) if m["body"].strip()}

def formula_shape(text):
    # Candidate-only: replace numeric literals, never use this as a merge identity.
    formulas=re.findall(r"\$(.*?)\$",text or "",re.S)
    if not formulas:return ""
    return "|".join(re.sub(r"(?<![A-Za-z])\d+(?:\.\d+)?", "#",canonical_text(x)) for x in formulas)

def classify(content,answer,solution,r):
    equal=same_question(content,r.content)
    conflict=answer_conflict(answer,r.answer)
    new=bool(method_keys(solution)-method_keys(r.solution))
    if equal:
        category="answer_conflict" if conflict else "new_method" if new else "same_question"
        return category, ("题干一致，答案存在差异，请核对" if conflict else "题干一致，存在新增解法" if new else "题干一致，无新增解法"),not conflict and not r.archived,new
    if question_stem_key(content)==r.stem_key:
        return "similar","旧规范化指纹相同，但原始数学内容不完全一致，需人工核对",False,False
    a,b=formula_shape(content),formula_shape(r.content)
    return "similar",("公式结构相近，数字、符号或条件需核对" if a and a==b else "题干文本相似，不能证明数学等价"),False,False

def search(db,kind,content,answer="",solution="",title="",threshold=.8,include_archived=False,exclude=None):
    """All active rows are eligible; return IDs first, then load only candidate objects.
    The existing indexed exact keys are retained. No recent-row limit or silent truncation."""
    fp=question_fingerprint(content,solution,answer) if kind=="question" else unit_fingerprint(title,content)
    stem=question_stem_key(content) if kind=="question" else None
    scope=[Resource.kind==kind]
    if not include_archived:scope.append(Resource.archived==False)
    if exclude:scope.append(Resource.id!=exclude)
    criteria=[Resource.fingerprint==fp]
    if stem:criteria.append(Resource.stem_key==stem)
    strict=list(db.execute(select(Resource.id,Resource.fingerprint,Resource.stem_key).where(*scope,or_(*criteria))))
    found={r.id:("exact" if r.fingerprint==fp else "same_stem",1.0) for r in strict}
    query=canonical_text(content);shape=formula_shape(content) if kind=="question" else ""
    scanned=0
    for ident,body,name in db.execute(select(Resource.id,Resource.content,Resource.title).where(*scope).execution_options(yield_per=100)):
        scanned+=1
        if ident in found:continue
        if kind=="knowledge" and title and canonical_text(title)==canonical_text(name):
            found[ident]=("same_title",1.0);continue
        if not query:continue
        other=canonical_text(body)
        # Long inputs still receive exact/stem matching. Similarity is bounded and marked candidate-only.
        matcher=SequenceMatcher(None,query[:6000],other[:6000])
        if matcher.real_quick_ratio()>=threshold and matcher.quick_ratio()>=threshold:
            score=matcher.ratio()
            if score>=threshold:found[ident]=("exact" if kind=="knowledge" and score==1 else "similar",score);continue
        if shape and shape==formula_shape(body):
            found[ident]=("similar",0.0)
    rows={}
    ids=list(found)
    for start in range(0,len(ids),300):
        rows.update({r.id:r for r in db.scalars(select(Resource).where(Resource.id.in_(ids[start:start+300]),*scope))})
    results=[]
    for ident,(match,score) in found.items():
        r=rows.get(ident)
        if r is None:continue
        if kind=="question":
            category,reason,mergeable,new=classify(content,answer,solution,r)
        else:category,reason,mergeable,new=match,"知识名称或正文匹配，需人工确认",False,False
        results.append(dict(resource=r,match_kind=match,similarity=round(score,3),category=category,reason=reason,mergeable=mergeable,appendable=mergeable and new,answer_conflict=category=="answer_conflict"))
    order={"answer_conflict":0,"same_question":1,"new_method":2,"exact":3,"same_title":4,"similar":5}
    results.sort(key=lambda x:(order.get(x["category"],6),x["resource"].archived,-x["similarity"],x["resource"].id))
    return results,scanned
