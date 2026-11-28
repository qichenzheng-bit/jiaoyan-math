from types import SimpleNamespace
import pytest
from app.core import native_work as n

def test_native_pilot_opt_in(monkeypatch):
    monkeypatch.delenv("WG_NATIVE_AGENT",raising=False)
    assert not n.enabled()
    monkeypatch.setenv("WG_NATIVE_AGENT","1")
    assert n.enabled()

def test_native_tools_no_nested_model_or_unbounded_permissions():
    tools={t["name"]:t for t in n.tools()}
    assert {"native_page","native_intake_review","question_search","selection_create"}<=tools.keys()
    assert not {"original_read","intake_text","video_generate","video_edit","model_usage","Bash"}&tools.keys()
    assert tools["native_intake_review"]["write"] and not tools["native_page"]["write"]

def test_native_page_passes_original_image_not_ocr(monkeypatch):
    f=SimpleNamespace(id="file",name="page.png",media_type="image/png")
    monkeypatch.setattr(n,"attached",lambda *a:(SimpleNamespace(total_units=1),f))
    monkeypatch.setattr(n.material_vision,"attachment",lambda *a:("image/png",b"original"))
    info,result=n.page_read(None,None,{"file_id":"file","page":1})
    assert info["page"]==1 and "data" not in info
    assert result["content"][1]=={"type":"image","mimeType":"image/png","data":"b3JpZ2luYWw="}

def test_native_page_rejects_out_of_range(monkeypatch):
    monkeypatch.setattr(n,"attached",lambda *a:(SimpleNamespace(total_units=1),SimpleNamespace()))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:n.page_read(None,None,{"file_id":"file","page":2})
    assert e.value.status_code==422

def test_draft_requires_read_evidence(monkeypatch):
    f=SimpleNamespace(id="file")
    monkeypatch.setattr(n,"attached",lambda *a:(SimpleNamespace(total_units=1),f))
    class DB:
        def get(self,*args):return None
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        n.draft_create(DB(),None,{"steps":[]},None,{"file_id":"file","title":"题目","pages":[{"page":1,"text":"题目"}],"items":[{"kind":"question"}]},"job")
    assert e.value.status_code==422

def test_native_word_reads_text_and_selected_image_without_ocr(monkeypatch):
    f=SimpleNamespace(id="word",name="math.docx",media_type=n.material_import.DOCX)
    monkeypatch.setattr(n,"attached",lambda *a:(SimpleNamespace(total_units=1),f))
    monkeypatch.setattr(n.storage,"file_path",lambda f:"fixture")
    def scan(path,page,handler):
        text=handler(1,"image/png",lambda:("image/png",b"original"))
        return {"text":"公式 "+text,"image_total":1,"warnings":[]}
    monkeypatch.setattr(n.word_images,"scan",scan)
    info,result=n.page_read(None,None,{"file_id":"word","page":1})
    assert info["image_total"]==1 and len(result["content"])==1
    info,result=n.page_read(None,None,{"file_id":"word","page":1,"image_index":1})
    assert info["image_index"]==1 and result["content"][1]["data"]=="b3JpZ2luYWw="

def test_native_word_draft_rejects_unread_embedded_image(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(n,"attached",lambda *a:(SimpleNamespace(total_units=1),SimpleNamespace(id="word")))
    class DB:
        def get(self,*args):return None
    reads=[{"tool":"native_page","state":"done","result":{"file_id":"word","page":1,"image_total":1}}]
    with pytest.raises(HTTPException,match="内嵌图片"):
        n.draft_create(DB(),None,{"steps":reads},None,{"file_id":"word","title":"题目","pages":[{"page":1,"text":"题目"}],"items":[{"kind":"question"}]},"job")

def test_native_attach_and_workspace_tools_registered():
    names={t["name"]:t for t in n.tools()}
    assert not names["native_workspace"]["write"]
    assert names["native_attach"]["write"]
    assert "replace_revision" in names["native_intake_review"]["parameters"]["properties"]
