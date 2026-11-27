from types import SimpleNamespace
from app.api.documents import merge_question_methods
from app.core.question_structure import QuestionData,Part,Method,project,digest,resolve
from app.core.question_matching import classify
from app.core.content_normalization import question_stem_key
from fastapi import HTTPException
import pytest

def resource(data):
    vals=project(data);qt="综合题"
    return SimpleNamespace(**vals,question_type=qt,question_data=data.model_copy(update={"legacy_digest":digest(vals["content"],vals["answer"],vals["solution"],qt)}).model_dump(),kind="question",archived=False,subject="高等数学",stem_key=question_stem_key(vals["content"]))
def test_partial_subquestion_answer_and_method_merge():
    old=QuestionData(stem="已知函数",subquestions=[Part(number=1,content="求导数",answer="2x",methods=[Method(body="公式法",recommended=True)]),Part(number=2,content="求极值")])
    r=resource(old)
    new=old.model_copy(update={"subquestions":[Part(number=1,content="求导数",methods=[Method(body="定义法")]),Part(number=2,content="求极值",answer="0",methods=[Method(body="导数判别")])]})
    vals=project(new)
    b={**vals,"kind":"question","question_type":"综合题","question_data":new.model_dump()}
    assert merge_question_methods(r,b,"高等数学")
    assert r.answer=="(1) 2x\n(2) 0"
    merged=resolve(r.content,r.answer,r.solution,r.question_type,r.question_data)
    assert [m.body for m in merged.subquestions[0].methods]==["公式法","定义法"]
    assert [m.recommended for m in merged.subquestions[0].methods]==[True,False]
    assert merged.subquestions[1].methods[0].recommended
    assert not merge_question_methods(r,b,"高等数学")
    conflict=new.model_copy(update={"subquestions":[Part(number=1,content="求导数",answer="3x"),new.subquestions[1]]})
    with pytest.raises(HTTPException):
        merge_question_methods(r,{**project(conflict),"kind":"question","question_type":"综合题","question_data":conflict.model_dump()},"高等数学")
