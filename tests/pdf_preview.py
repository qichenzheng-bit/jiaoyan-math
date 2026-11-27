"""Exercise the production PDF renderer against the exact compiled frontend."""
import base64
import json
import time
import os
import sys
import tempfile
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.document_pdf import render_pdf, selected_pages

# Hosted runner only. Production launch keeps Chromium sandbox enabled.
os.environ["WG_PDF_CHROMIUM_SANDBOX"] = "0"

def block(uid, kind, content="", **kw):
    return dict(uid=uid, kind=kind, content=content, title="", answer="",
                solution="", analysis="", proof="", file_id=None, width=100, **kw)

def run():
    assert selected_pages("1-2,2，4",5)==[0,1,3]
    for invalid in ("0","3-2","6","1,,2","abc"):
        try:selected_pages(invalid,5)
        except ValueError:pass
        else:raise AssertionError(invalid)
    blocks = [
        {**block("chapter-one", "heading", heading_level=1), "title": "第一章 Chapter One"},
        {**block("question-one", "question", r"MarkerAlpha 求极限 $ \lim_{x\to0}\frac{\sin x}{x} $"), "answer": "HiddenAnswerAlpha"},
        block("page-break", "pagebreak"),
        {**block("chapter-two", "heading", heading_level=1), "title": "第二章 Chapter Two"},
        block("question-two", "question", r"MarkerBeta 计算 $\int_0^1 x^2\,dx$"),
    ]
    for i in range(80):
        blocks.append(block("extra-"+str(i), "question", "ScaleMarker"+str(i)+" 练习题 $x^2+1$"))
    payload = {
        "doc": {"title": "数学讲义 Layout Test", "subject": "高等数学", "kind": "handout", "blocks": blocks},
        "layout": {"paper": "A4", "columns": 1, "toc": True, "chapterNewPage": True,
                   "footer": "第 {{当前页码}} 页，共 {{总页数}} 页", "equationNumbering":"chapter"},
        "stem": True, "answerOnly": False, "source": False,
    }
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)
        (path/"payload.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = render_pdf(path/"payload.json", {}, path/"result.pdf", print, lambda: False, ROOT/"frontend"/"dist")
        assert result and result["pages"] >= 3, result
        reader = PdfReader(path/"result.pdf")
        assert len(reader.pages) == result["pages"]
        text = "\n".join(p.extract_text() for p in reader.pages)
        for marker in ("MarkerAlpha", "MarkerBeta", "ScaleMarker79"):
            assert marker in text, marker
        assert "HiddenAnswerAlpha" not in text
        assert "(2.1)" in "".join(text.split()), text
        for page in reader.pages:
            assert abs(float(page.mediabox.width) - 595.28) < 1.5
            assert abs(float(page.mediabox.height) - 841.89) < 1.5
        print("PDF pagination, searchable text, student mode and A4 dimensions:", result)
        payload["page_ranges"]="2"
        payload["preview_pages"]=result["pages"]
        (path/"payload.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
        subset=render_pdf(path/"payload.json", {}, path/"subset.pdf", print, lambda: False, ROOT/"frontend"/"dist")
        assert subset["pages"]==1 and subset["total_pages"]==result["pages"]
        assert PdfReader(path/"subset.pdf").pages[0].extract_text()==reader.pages[1].extract_text()
        payload.pop("page_ranges");payload.pop("preview_pages")
        # Mixed paper sizes, linked knowledge index, and saved cover assets.
        cover_id="e59eb181-5574-4dbc-a272-7246d2d0d069"
        image=path/"cover.png"
        image.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3J0AAAAASUVORK5CYII="))
        images={"/api/files/"+cover_id+"/preview":(str(image),"image/png")}
        payload["doc"]["blocks"]=[
            *blocks[:5],
            {**block("index-entry","knowledge","Knowledge content"),"title":"IndexMarker","knowledge_tags":["GraphTagNotForIndex"]},
        ]
        payload["layout"].update(sectionPages={"chapter-two":{"paper":"A5","landscape":True}},knowledgeIndex=True,coverFileId=cover_id,backCoverFileId=cover_id)
        (path/"payload.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
        combined=render_pdf(path/"payload.json",images,path/"combined.pdf",print,lambda:False,ROOT/"frontend"/"dist")
        reader2=PdfReader(path/"combined.pdf")
        assert combined["pages"]==len(reader2.pages)
        sizes=[(float(p.mediabox.width),float(p.mediabox.height)) for p in reader2.pages]
        assert any(abs(w-595.28)<1.5 and abs(h-419.53)<1.5 for w,h in sizes),sizes
        assert all(abs(sizes[i][0]-595.28)<1.5 and abs(sizes[i][1]-841.89)<1.5 for i in (0,-1)),sizes
        combined_text="\n".join(p.extract_text() for p in reader2.pages)
        assert combined_text.count("IndexMarker")>=2
        assert "GraphTagNotForIndex" not in combined_text
        assert not reader2.pages[0].extract_text().strip() and not reader2.pages[-1].extract_text().strip()
        print("Mixed page geometry, knowledge index and cover verification:",sizes)
        payload["layout"]={"paper":"A4","columns":1}
        payload["doc"]["blocks"] = [block("bad", "question", r"$\unknowncommand$")]
        (path/"payload.json").write_text(json.dumps(payload), encoding="utf-8")
        try:
            render_pdf(path/"payload.json", {}, path/"invalid.pdf", print, lambda: False, ROOT/"frontend"/"dist")
        except ValueError:
            assert not (path/"invalid.pdf").exists()
        else:
            raise AssertionError("Invalid math must block PDF output")

def scale():
    count=int(os.environ.get("WG_PDF_SCALE","0"))
    if not count:return
    rows=[]
    for i in range(count):
        if i%200==0:
            rows.append({**block("chapter-"+str(i),"heading",heading_level=1),"title":"Chapter "+str(i//200+1)})
        rows.append(block("item-"+str(i),"question","ScaleRow%05d"%i+(r" $x^2+1$" if i%25==0 else " 练习")))
    payload={"doc":{"title":"Large Layout","subject":"高等数学","kind":"textbook","blocks":rows},
             "layout":{"paper":"A4","toc":True,"chapterNewPage":True},"stem":True,"answerOnly":False,"source":False}
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)
        (path/"payload.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
        started=time.monotonic()
        result=render_pdf(path/"payload.json",{},path/"scale.pdf",print,lambda:False,ROOT/"frontend"/"dist")
        text="\n".join(p.extract_text() for p in PdfReader(path/"scale.pdf").pages)
        import re
        found=set(re.findall(r"ScaleRow\d{5}",text))
        assert len(found)==count,(len(found),count)
        print("Scale:",count,"items",result,"seconds",round(time.monotonic()-started,2))

if __name__ == "__main__":
    run()
    scale()
