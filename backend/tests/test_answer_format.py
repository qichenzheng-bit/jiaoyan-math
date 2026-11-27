from app.core.answer_format import answer_format_prompt

def test_answer_format_contract():
    p=answer_format_prompt()
    for phrase in ("最终结果","每个小问","recommended","aligned","不修改数学内容","不编造"):
        assert phrase in p

def test_regenerated_solution_preserves_other_fields():
    import pytest
    from app.api.documents import Block
    from app.api.intelligence import apply_regenerated_solution
    original=Block(uid="q1",kind="question",title="计算",content="求极限",answer="$1$",solution="AI旧解",knowledge_tags=["函数极限","连续"],primary_knowledge_tag="函数极限",generated_fields=["solution"]).model_dump()
    updated=apply_regenerated_solution(original,"解：新解。")
    assert updated["solution"]=="解：新解。"
    for field in ("uid","title","content","answer","knowledge_tags","primary_knowledge_tag"):
        assert updated[field]==original[field]
    with pytest.raises(ValueError):apply_regenerated_solution({**original,"generated_fields":[]},"不能覆盖原文")
    with pytest.raises(ValueError):apply_regenerated_solution(original,"")

def test_multiple_methods_have_exactly_one_recommendation():
    from app.core.question_structure import QuestionData
    data=QuestionData(stem="题目",methods=[{"body":"方法A","recommended":True},{"body":"方法B","recommended":True}])
    assert [m.recommended for m in data.methods]==[True,False]
    data=QuestionData(stem="题目",methods=[{"body":""},{"body":"非空方法"}])
    assert [m.recommended for m in data.methods]==[False,True]
