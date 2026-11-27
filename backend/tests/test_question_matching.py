from types import SimpleNamespace
from app.core.question_matching import same_question, classify, formula_shape
from app.core.content_normalization import question_stem_key

def row(content,answer,solution):
    return SimpleNamespace(content=content,answer=answer,solution=solution,stem_key=question_stem_key(content),archived=False)

def test_question_identity_not_solution_identity():
    q=r"求 $\int xe^x dx$"
    assert classify(q,"1","第二种方法",row(q,"1","第一种方法"))[0]=="new_method"
    assert classify(q,"-1","第二种方法",row(q,"1","第一种方法"))[0]=="answer_conflict"
    assert classify(q,"1","第一种方法",row(q,"1","第一种方法"))[0]=="same_question"

def test_math_conditions_not_erased():
    assert not same_question(r"$\lim_{x\to0}x$",r"$\lim_{x\to1}x$")
    assert not same_question("$x²$","$x2$")
    assert not same_question("$-x$","$x$")
    assert formula_shape(r"$\int_0^1 x^2 dx$")==formula_shape(r"$\int_0^2 x^3 dx$")
    assert not classify("$x²$","","",row("$x2$","",""))[2]
