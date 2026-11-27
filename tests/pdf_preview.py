"""Exercise the production PDF renderer against the exact compiled frontend."""
import json
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
        payload["doc"]["blocks"] = [block("bad", "question", r"$\unknowncommand$")]
        (path/"payload.json").write_text(json.dumps(payload), encoding="utf-8")
        try:
            render_pdf(path/"payload.json", {}, path/"invalid.pdf", print, lambda: False, ROOT/"frontend"/"dist")
        except ValueError:
            assert not (path/"invalid.pdf").exists()
        else:
            raise AssertionError("Invalid math must block PDF output")

if __name__ == "__main__":
    run()
