import pytest
from types import SimpleNamespace
from app.services.recognition_plan import parse_instruction,matching_names,propose_range

@pytest.mark.parametrize("text,start,count",[
    ("继续识别五页",None,5),("后面的10页",None,10),("识别第21至30页",21,10),
    ("从第21页开始识别5页",21,5),("重新识别第8页",8,1),
    ("教材.pdf 继续识别两页",None,2),("接着处理 3 页",None,3),
])
def test_parse_range(text,start,count):
    p=parse_instruction(text)
    assert (p["start"],p["count"])==(start,count)
@pytest.mark.parametrize("text",["识别全部", "识别11页","识别第30至21页","识别第0页","识别第9999至10002页","识别第1页和第2页"])
def test_invalid_range(text):
    with pytest.raises(ValueError):parse_instruction(text)

def test_plan_pending_overlap_and_bounds():
    b=SimpleNamespace(id="x",start=1,end=10,verified_text="checked")
    assert propose_range({"start":None,"count":10},[b],14,11)["end"]==14
    assert propose_range({"start":5,"count":1},[b],20,11)["batch_id"]=="x"
    assert propose_range({"start":8,"count":4},[b],20,11)["blocked"]
    b.verified_text=None
    assert propose_range({"start":None,"count":5},[b],20,1)["batch_id"]=="x"
    assert propose_range({"start":None,"count":5},[],20,21)["blocked"]

def test_names_never_guess():
    files=[SimpleNamespace(name="同济高等数学上册.pdf"),SimpleNamespace(name="同济高等数学下册.pdf")]
    assert len(matching_names(files,"高等数学 继续识别5页","高等数学"))==2
    assert matching_names(files,"同济高等数学上册.pdf 继续识别5页","")==files[:1]
    assert matching_names(files,"不存在的文件 继续识别5页","不存在的文件")==[]


def test_context_hint():
    assert parse_instruction("继续识别五页")["hint"]==""
    assert parse_instruction("重新识别第8页")["hint"]==""
    assert parse_instruction("前边那个未识别完的教材继续识别十页")["unfinished"]
    assert parse_instruction("高等数学，继续识别5页")["hint"]=="高等数学"
