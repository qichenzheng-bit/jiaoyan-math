from app.core.answer_format import answer_format_prompt

def test_answer_format_contract():
    p=answer_format_prompt()
    for phrase in ("最终结果","每个小问","recommended","aligned","不修改数学内容","不编造"):
        assert phrase in p
