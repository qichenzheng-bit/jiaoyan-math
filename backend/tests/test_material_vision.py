import pytest
from fastapi import HTTPException
from app.services import material_vision as v

def test_decode_reply():
    assert v.decode_reply(r'{"text":"$x^2$"}')=="$x^2$"
    assert v.decode_reply(' ```json\n{"text":"题目"}\n``` ')=="题目"

@pytest.mark.parametrize("raw",["无法识图",'{"text":""}','{"text":null}','[]','{"text":2}'])
def test_invalid_replies(raw):
    with pytest.raises(HTTPException):
        v.decode_reply(raw)

def test_ocr_fallback_is_labeled(monkeypatch):
    def fail(*args): raise HTTPException(503,"worker old")
    monkeypatch.setattr(v,"extract",fail)
    monkeypatch.setattr(v.imp,"extract",lambda *a:{"text":"OCR","method":"image_ocr","warnings":[]})
    result=v.recognize(None,1,"Auto")
    assert result["method"]=="image_ocr"
    assert "worker old" in result["warnings"][0]

def test_busy_does_not_fall_back(monkeypatch):
    def fail(*args): raise HTTPException(409,"busy")
    monkeypatch.setattr(v,"extract",fail)
    monkeypatch.setattr(v.imp,"extract",lambda *a:pytest.fail("unexpected OCR fallback"))
    with pytest.raises(HTTPException) as e: v.recognize(None,1,"Auto")
    assert e.value.status_code==409

def test_vision_calls_real_attachment_endpoint(monkeypatch):
    calls=[]
    def request(method,path,body=None):
        calls.append((method,path,body))
        if path=="/status": return {"vision_attachment":True,"chat_available":True}
        if path=="/vision/start": return {"state":"running"}
        return {"state":"done","answer":'{"text":"公式"}'}
    monkeypatch.setattr(v.qoder,"request",request)
    monkeypatch.setattr(v,"attachment",lambda *a:("image/png",b"test"))
    result=v.extract(None,1,"DeepSeek-Flash")
    assert result["method"]=="qoder_vision"
    assert calls[1][1]=="/vision/start"
    assert calls[1][2]["attachment"]=={"media_type":"image/png","base64":"dGVzdA=="}
    assert calls[1][2]["model"]=="DeepSeek-Flash"

def test_pdf_vision_precedes_text_and_uses_text_fallback(monkeypatch):
    from types import SimpleNamespace
    f=SimpleNamespace(media_type="application/pdf")
    calls=[]
    def extract(*args):
        calls.append("vision")
        raise HTTPException(422,"vision failed")
    def local(file,mode,start,end):
        calls.append(mode)
        return {"text":"pdf text","method":"pdf_text","warnings":[]}
    monkeypatch.setattr(v,"extract",extract)
    monkeypatch.setattr(v.imp,"extract",local)
    result=v.recognize(f,2,"DeepSeek-Flash")
    assert calls==["vision","text"]
    assert result["method"]=="pdf_text" and "vision failed" in result["warnings"][0]

def test_pdf_vision_success_does_not_extract_text(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(v,"extract",lambda *a:{"text":"$x^2$","method":"qoder_vision","warnings":[]})
    monkeypatch.setattr(v.imp,"extract",lambda *a:pytest.fail("text layer must not override vision"))
    assert v.recognize(SimpleNamespace(media_type="application/pdf"),1,"Auto")["method"]=="qoder_vision"
