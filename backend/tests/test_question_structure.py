import json
import pytest
from pydantic import ValidationError
from app.core.question_structure import QuestionData, derive
from app.api.documents import Block
from app.api.resources import Draft
from app.api.intelligence import parse_answer, apply_supplement

def test_explicit_structure_and_compatibility_projection():
    data={"version":1,"stem":"求极限 $x$","options":[{"label":"A","content":"$-1$"},{"label":"B","content":"$1$"}],"correct_options":["B"],"methods":[{"name":"直接法","body":"原解法","recommended":True}]}
    b=Block(uid="a",kind="question",title="选择题",question_type="单选题",question_data=data)
    assert b.content=="求极限 $x$\nA. $-1$\nB. $1$" and b.answer=="B"
    assert b.question_data.options[0].content=="$-1$"
    assert b.question_data.methods[0].name=="直接法"
    draft=Draft.model_validate({**b.model_dump(),"kind":"question","subject":"高等数学"})
    assert draft.question_data==b.question_data
    changed=Draft.model_validate({**draft.model_dump(),"answer":"A"})
    assert changed.answer=="A" and changed.question_data.correct_options==["A"]

def test_legacy_ambiguous_parts_never_rewrite_text():
    raw={"kind":"question","uid":"x","title":"综合题","question_type":"综合题","content":"公共\n(1) 题一\n(2) 题二","answer":"公共答案\n(1) 1","solution":"公共解法"}
    b=Block.model_validate(raw)
    assert (b.content,b.answer,b.solution)==(raw["content"],raw["answer"],raw["solution"])
    assert b.question_data.warnings and not b.question_data.subquestions

def test_independent_subquestions():
    b=Block(uid="x",kind="question",title="综合",question_type="综合题",question_data={"stem":"已知函数","subquestions":[{"number":1,"content":"单调性","answer":"递增","methods":[{"body":"解法一"}]},{"number":2,"content":"极值","answer":"0"}]})
    assert b.answer=="(1) 递增\n(2) 0"
    assert b.question_data.subquestions[1].answer=="0"
    with pytest.raises(ValidationError):QuestionData(stem="x",answer="不应有",subquestions=[{"number":1}])
    with pytest.raises(ValidationError):QuestionData(stem="x",options=[{"label":"A"}],correct_options=["B"])

def test_ai_and_manual_share_structure_and_keep_missing_answers():
    raw={"kind":"question","title":"求导","question_type":"综合题","question_data":{"stem":"求 $x^2$ 的导数"}}
    item=parse_answer(json.dumps([raw]))[0]
    assert item["answer"]==item["solution"]==""
    assert item["question_data"]["stem"]=="求 $x^2$ 的导数"
    changed=apply_supplement(item,{"answer":"$2x$"},["answer"])
    assert changed["question_data"]["answer"]=="$2x$" and changed["content"]==item["content"]

def test_fill_blanks_and_no_guessed_split():
    text=r"$\underline{\qquad}$ 加 $\underline{\qquad}$"
    b=Block(uid="x",kind="question",title="填空",question_type="填空题",question_data={"stem":text,"blanks":[{"number":1,"answer":"1"},{"number":2,"answer":"2"}]})
    assert b.answer=="(1) 1\n(2) 2"
    assert derive(text,"1, 2","","填空题").warnings
    with pytest.raises(ValidationError):Block(uid="x",kind="question",title="填空",question_type="填空题",question_data={"stem":text,"blanks":[{"number":1}]})

def test_legacy_text_and_structure_conflict_is_not_silent():
    with pytest.raises(ValidationError):Block(uid="x",kind="question",title="题",content="原题",question_data={"stem":"其他题"})
