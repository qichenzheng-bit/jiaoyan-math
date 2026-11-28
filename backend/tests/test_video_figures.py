import base64
import importlib.util
import io
from pathlib import Path
import pytest
from PIL import Image
from fastapi import HTTPException
from app.services.video_figures import prepare
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("figures_bridge",ROOT/"vendor/video-overlay/app/backend/src/weiguang_backend/pipeline/video_figures_bridge.py")
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)

def test_reference_numbers_follow_first_occurrence():
    a="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";b="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    raw={"problem":f"图[[img:{b}:50]]与[[img:{a}:80]]","reference_solution":f"如图[[img:{b}:50]]"}
    result,ids=prepare(raw)
    assert ids==[b,a]
    assert result["problem"]=="图[参考附图1]与[参考附图2]"
    assert result["reference_solution"]=="如图[参考附图1]"
    with pytest.raises(HTTPException):prepare({"problem":"![图](https://example.com/a.png)"})

def test_contact_sheet_preserves_original_pixels(tmp_path):
    records=[]
    for color in ("red","blue"):
        out=io.BytesIO();Image.new("RGB",(100,80),color).save(out,format="PNG")
        records.append({"media_type":"image/png","base64":base64.b64encode(out.getvalue()).decode()})
    refs=bridge.store(tmp_path,bridge.decode(records))
    result=bridge.cli_attachment([r["path"] for r in refs])
    with Image.open(io.BytesIO(base64.b64decode(result["base64"]))) as im:
        assert im.size==(264,144)
        assert im.getpixel((30,60))==(255,0,0)
        assert im.getpixel((160,60))==(0,0,255)
    with pytest.raises(ValueError):bridge.decode([{"media_type":"image/png","base64":"not valid"}])
