from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.services import pdf_text

def test_pdf_type_and_page_limits():
    with pytest.raises(HTTPException) as e:
        pdf_text.extract_pdf(SimpleNamespace(archived=False,media_type="text/plain"),1,1)
    assert e.value.status_code==415
    with pytest.raises(HTTPException) as e:
        pdf_text.extract_pdf(SimpleNamespace(archived=False,media_type="application/pdf"),1,11)
    assert e.value.status_code==422

def test_extraction_uses_bounded_no_shell_subprocess(tmp_path,monkeypatch):
    monkeypatch.setattr(pdf_text.shutil,"which",lambda name:"/usr/bin/"+name)
    monkeypatch.setattr(pdf_text.storage,"file_path",lambda f:tmp_path/"file")
    def fake_run(args,**kwargs):
        assert args[:5]==["/usr/bin/prlimit","--as=536870912","--fsize=262144","--cpu=15","--"]
        assert kwargs["timeout"]==20
        kwargs["stdout"].write("题目".encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(pdf_text.subprocess,"run",fake_run)
    assert pdf_text.extract_pdf(SimpleNamespace(archived=False,media_type="application/pdf"),2,3)=="题目"
