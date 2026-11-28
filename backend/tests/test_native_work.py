from types import SimpleNamespace
import pytest
from app.core import native_work as n

def test_native_tools_no_nested_model_or_unbounded_permissions():
    tools={t["name"]:t for t in n.tools()}
    assert {"native_page","native_intake_review","question_search","selection_create"}<=tools.keys()
    assert not {"original_read","intake_text","Bash"}&tools.keys()
    assert {"native_text_review","model_usage","model_catalog","checkin_state","intake_status"}<=tools.keys()
    assert {"video_generate","video_render","video_edit","video_retry","video_job_read"}<=tools.keys()
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


def test_native_video_waits_for_real_render(monkeypatch):
    from types import SimpleNamespace
    from app.core import native_work as n
    from app.api import work_agent as wa
    record={"phase_at":n.now(),"steps":[{"state":"queued","video_child":{"kind":"video","project":"p","id":"g"}}]}
    monkeypatch.setattr(wa,"save",lambda *args:None)
    db=SimpleNamespace(commit=lambda:None)
    monkeypatch.setattr(n.video,"job_read",lambda *args:{"id":"g","kind":"generate","status":"succeeded"})
    monkeypatch.setattr(n.video,"followup_render",lambda *args:{"id":"r","kind":"render","status":"queued"})
    n.poll_video_jobs(db,None,record,None)
    assert record["steps"][0]["video_child"]["id"]=="r"
    assert record["steps"][0]["state"]=="queued"
    monkeypatch.setattr(n.video,"job_read",lambda *args:{"id":"r","kind":"render","status":"succeeded"})
    n.poll_video_jobs(db,None,record,None)
    assert record["state"]=="done" and record["steps"][0]["state"]=="done"

def test_native_video_tool_is_async():
    from app.core import native_work as n
    specs={x["name"]:x for x in n.tools()}
    for name in n.VIDEO_JOBS:
        assert "结束本轮" in specs[name]["description"]


def test_native_text_review_cannot_bypass_attachment_reading(monkeypatch):
    from fastapi import HTTPException
    from app.core import native_work as n
    monkeypatch.setattr(n,"current_files",lambda *a:[{"file":{"id":"original"}}])
    with pytest.raises(HTTPException) as exc:
        n.create_text_draft(None,None,{},None,{"title":"文字","text":"题","items":[{"kind":"question"}]},"draft")
    assert exc.value.status_code==422


def test_native_completion_does_not_hide_failed_tool():
    r={"steps":[{"state":"done"},{"state":"failed"}]}
    n.complete_turn(r,"模型说完成")
    assert r["state"]=="failed"
    r["steps"][1]["state"]="recovered"
    n.complete_turn(r,"已修复")
    assert r["state"]=="done"

def test_native_detail_pagination_preserves_full_content(monkeypatch):
    import json
    monkeypatch.setattr(n.ai_tools,"execute",lambda *a,**k:{"content":"数学"*12000})
    first=n.read_detail(None,None,{"tool":"resource_read","args":{"id":"x"}})
    text=first["text"];page=first
    while page["next_offset"] is not None:
        page=n.read_detail(None,None,{"tool":"resource_read","args":{"id":"x"},"offset":page["next_offset"],"digest":first["digest"]})
        text+=page["text"]
    assert json.loads(text)=={"content":"数学"*12000}
    with pytest.raises(n.HTTPException):n.read_detail(None,None,{"tool":"video_generate","args":{}})

def test_native_draft_requires_complete_answers_and_solutions():
    b={"kind":"question","title":"极限","content":"求极限","answer":"","solution":"","knowledge_tags":["极限","连续"],"primary_knowledge_tag":"极限"}
    with pytest.raises(n.HTTPException):n.validate_draft_items([b])
    n.validate_draft_items([{**b,"answer":"0","solution":"由连续性得0"}])

def test_amended_turn_retains_original_if_no_session(monkeypatch):
    monkeypatch.setattr(n,"user_prompt",lambda db,s,prompt,selected=None:prompt)
    r={"instruction":"原题","amendments":[{"text":"改成第二页"}],"steps":[],"native_amendment_count":0}
    assert n.next_amended_turn(None,None,r)
    assert "原题" in r["native_prompt"] and "改成第二页" in r["native_prompt"]
    assert not n.pending_amendments(r)


def test_native_reference_preserves_literal_excerpt_and_unverified_status(monkeypatch):
    f=SimpleNamespace(id="ref",name="答案.pdf",media_type="application/pdf")
    monkeypatch.setattr(n,"attached",lambda *a:(SimpleNamespace(id="material",total_units=3),f))
    body=n.Draft(file_id="main",title="题目",pages=[n.Transcript(page=1,text="题干")],items=[{}],
        reference_pages=[n.ReferencePage(file_id="ref",page=2,text="答案：0\n解析：由连续性得0")],
        reference_fields=[n.ReferenceField(item_index=0,field="answer",file_id="ref",page=2)])
    r={"steps":[{"tool":"native_page","state":"done","result":{"file_id":"ref","page":2}}]}
    items=[{"uid":"q","kind":"question","answer":"0"}]
    result,ids=n.reference_provenance(None,SimpleNamespace(id="work"),r,body,items,"main")
    assert ids=={"ref"} and result["q"]["answer"]["page"]==2 and not result["q"]["answer"]["verified"]
    with pytest.raises(n.HTTPException):n.reference_provenance(None,SimpleNamespace(id="work"),r,body,[{**items[0],"answer":"1"}],"main")
    with pytest.raises(n.HTTPException):n.reference_provenance(None,SimpleNamespace(id="work"),{"steps":[]},body,items,"main")
    with pytest.raises(n.HTTPException):n.reference_provenance(None,SimpleNamespace(id="work"),r,body,[{**items[0],"generated_fields":["answer"]}],"main")

def test_native_boundary_missing_requires_actual_pages(monkeypatch):
    monkeypatch.setattr(n,"attached",lambda *a:(SimpleNamespace(total_units=2),SimpleNamespace(id="f")))
    class DB:
        def get(self,*a):return None
    with pytest.raises(n.HTTPException,match="边界"):
        n.draft_create(DB(),None,{"steps":[]},None,{"file_id":"f","title":"题","pages":[{"page":1,"text":"题干"}],"items":[{}],"incomplete_boundary":"第2题解析在下一页"},"j")


def test_native_restart_recovers_only_read_only_turn(monkeypatch):
    monkeypatch.setattr(n,"user_prompt",lambda db,s,prompt,selected=None:prompt)
    record={"instruction":"读第2页","steps":[{"tool":"native_page","state":"done"}],"native_session":"old",
        "amendments":[{"text":"再读第3页"}]}
    assert n.resume_read_only(None,None,record)
    assert record["native_resume"]=="old" and record["phase"]=="pending"
    assert "读第2页" in record["native_prompt"] and "再读第3页" in record["native_prompt"]
    assert not n.resume_read_only(None,None,record)
    assert not n.resume_read_only(None,None,{"steps":[{"tool":"native_intake_review","state":"done"}]})
    assert n.uncertain_write({"steps":[{"tool":"native_intake_review","state":"running"}]})


def test_work_entry_uses_native_even_when_old_flags_are_unset(monkeypatch):
    from unittest.mock import Mock
    from app.api import work_agent as wa
    monkeypatch.delenv("WG_NATIVE_AGENT",raising=False)
    db=Mock();user=SimpleNamespace(id=1);s=SimpleNamespace(agent_history=[])
    monkeypatch.setattr(n.w,"workspace",lambda *a:s)
    begin=Mock(return_value={"native":True});monkeypatch.setattr(n,"begin",begin)
    assert wa.start("w",wa.Start(instruction="新的任务",auto=False),db,user)=={"native":True}
    begin.assert_called_once()
