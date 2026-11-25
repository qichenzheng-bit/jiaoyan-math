import pytest
from app.api.intelligence import parse_answer
def test_extraction():
    rows=parse_answer('[{"kind":"question","title":"极限","content":"求极限"}]')
    assert rows[0]["kind"]=="question" and rows[0]["answer"]==""
    with pytest.raises(ValueError):
        parse_answer('[{"kind":"reference","title":"x","content":"x"}]')
