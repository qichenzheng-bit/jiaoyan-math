from types import SimpleNamespace
import zipfile
import pytest
from fastapi import HTTPException
from app.services import material_import as imp

def test_docx_order_math_and_missing_objects(tmp_path,monkeypatch):
    path=tmp_path/"test.docx"
    xml="""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body>
    <w:p><w:r><w:t>求</w:t></w:r><m:oMath><m:f><m:num><m:r><m:t>1</m:t></m:r></m:num><m:den><m:r><m:t>x</m:t></m:r></m:den></m:f></m:oMath></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>甲</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>乙</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    <w:p><w:r><w:drawing/></w:r><m:oMath><m:nary/></m:oMath></w:p></w:body></w:document>"""
    with zipfile.ZipFile(path,"w") as z:z.writestr("word/document.xml",xml)
    monkeypatch.setattr(imp.storage,"file_path",lambda f:path)
    result=imp.extract(SimpleNamespace(archived=False,media_type=imp.DOCX),"text",1,100)
    assert result["text"].startswith(r"求$\frac{1}{x}$")
    assert "甲 | 乙" in result["text"]
    assert "[Word公式待核对]" in result["text"] and result["total_units"]==3
    assert result["end"]==3 and result["warnings"]

def test_unsafe_xml_rejected(tmp_path):
    path=tmp_path/"bad.docx"
    with zipfile.ZipFile(path,"w") as z:z.writestr("word/document.xml",'<!DOCTYPE x [<!ENTITY e "abc">]><x>&e;</x>')
    with pytest.raises(HTTPException):imp.docx_blocks(path)

def test_ocr_is_disabled(tmp_path,monkeypatch):
    monkeypatch.setattr(imp.storage,"file_path",lambda f:tmp_path/"scan.pdf")
    f=SimpleNamespace(archived=False,media_type="application/pdf")
    with pytest.raises(HTTPException) as e:imp.extract(f,"ocr",1,1)
    assert e.value.status_code==410

def test_capabilities_never_offer_ocr(monkeypatch):
    monkeypatch.setattr(imp.shutil,"which",lambda name:"/usr/bin/"+name)
    cap=imp.capabilities()
    assert cap["pdf_text"] and not cap["image_ocr"] and not cap["pdf_ocr"]
