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
