from app.core.content_normalization import question_fingerprint
from app.core.solution_methods import normalize_subject, parse_methods
def test_legacy_rules():
    assert normalize_subject("高数")=="高等数学"
    assert question_fingerprint(r"$\\frac{1}{2}$","","") != question_fingerprint(r"$\\frac{1}{3}$","","")
    assert question_fingerprint("Ａ","","")==question_fingerprint("A","","")
    assert len(parse_methods("### ※ 方法一\n甲\n### 方法二\n乙"))==2
