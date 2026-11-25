import pytest
from app.api.intelligence import parse_answer
def test_extraction():
    rows=parse_answer('[{"kind":"question","title":"极限","content":"求极限"}]')
    assert rows[0]["kind"]=="question" and rows[0]["answer"]==""
    with pytest.raises(ValueError):
        parse_answer('[{"kind":"reference","title":"x","content":"x"}]')

from app.api.chat import split_intake_intent

def test_intent_protocol_is_exact_and_not_an_action():
    assert split_intake_intent("请确认录入。\n[[WG_INTAKE:question]]")==("请确认录入。","question")
    for text in ("普通答疑","[[WG_INTAKE:question]]","正文\n[[WG_INTAKE:delete]]","正文\n[[WG_INTAKE:question]]\n后文"):
        assert split_intake_intent(text)==(text,None)
