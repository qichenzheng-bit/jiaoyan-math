from app.core.bank_filter_facts import filter_facts
from app.core.question_structure import QuestionData,Part,Method,project,digest

def test_part_completeness_and_methods():
    data=QuestionData(stem="函数",subquestions=[Part(number=1,content="求导",answer="1",methods=[Method(body="泰勒公式",recommended=True),Method(body="直接计算")]),Part(number=2,content="求极值")])
    raw=project(data)
    stored=data.model_copy(update={"legacy_digest":digest(**raw,question_type="综合题")}).model_dump()
    facts=filter_facts(**raw,question_type="综合题",stored=stored)
    assert facts["multi"] and not facts["answer_complete"] and not facts["solution_complete"]
    assert facts["method:泰勒展开"]
