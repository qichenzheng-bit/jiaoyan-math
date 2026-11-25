"""Bounded material import; OCR is local text recognition, never mathematical verification."""
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError
from fastapi import HTTPException
from app.services import storage
from app.services.pdf_text import extract_pdf

DOCX="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT={"text/plain","text/csv"}
W="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M="{http://schemas.openxmlformats.org/officeDocument/2006/math}"
MAX_TEXT=24000

def capabilities():
    limiter=bool(shutil.which("prlimit"))
    languages=[]
    if limiter and shutil.which("tesseract"):
        try:
            result=subprocess.run([shutil.which("prlimit"),"--as=536870912","--cpu=3","--",shutil.which("tesseract"),"--list-langs"],capture_output=True,timeout=5,check=False)
            if result.returncode==0:languages=result.stdout.decode("utf-8",errors="replace").splitlines()
        except (OSError,subprocess.TimeoutExpired):pass
    ocr="eng" in languages and "chi_sim" in languages
    return {"text":True,"docx":True,"pdf_text":bool(limiter and shutil.which("pdftotext")),
            "image_ocr":ocr,"pdf_ocr":bool(ocr and shutil.which("pdftoppm"))}

def latex(node,depth=0):
    if depth>32:raise ValueError("nested formula")
    tag=node.tag.removeprefix(M)
    def part(name):
        child=node.find(M+name)
        return latex(child,depth+1) if child is not None else ""
    def group(name):return "{"+part(name)+"}"
    if tag=="t":
        t=node.text or ""
        # Do not treat arbitrary embedded text as executable LaTeX.
        if any(c in t for c in "\\{}$%&#_"):raise ValueError("complex math text")
        return t
    if tag in ("oMath","oMathPara","e","num","den","sub","sup","deg","r","lim"):
        return "".join(latex(c,depth+1) for c in node if not c.tag.endswith("Pr"))
    if tag=="f":return r"\frac"+group("num")+group("den")
    if tag=="sSup":return group("e")+"^"+group("sup")
    if tag=="sSub":return group("e")+"_"+group("sub")
    if tag=="sSubSup":return group("e")+"_"+group("sub")+"^"+group("sup")
    if tag=="rad":return r"\sqrt"+("["+part("deg")+"]" if part("deg") else "")+group("e")
    if tag in ("limLow","limUpp"):return group("e")+("_" if tag=="limLow" else "^")+group("lim")
    if tag=="m":
        rows=[" & ".join(latex(c,depth+1) for c in r.findall(M+"e")) for r in node.findall(M+"mr")]
        if not rows:raise ValueError("empty matrix")
        return r"\begin{matrix}"+r"\\".join(rows)+r"\end{matrix}"
    if tag=="d":
        # Delimiter types and properties must not be guessed.
        pr=node.find(M+"dPr")
        if pr is not None and any(c.tag not in (M+"ctrlPr",) for c in pr):raise ValueError("custom delimiter")
        return r"\left("+"".join(latex(c,depth+1) for c in node.findall(M+"e"))+r"\right)"
    raise ValueError("unsupported formula")

def docx_blocks(path):
    warnings=set()
    try:
        with zipfile.ZipFile(path) as z:
            info=z.getinfo("word/document.xml")
            if info.file_size>8_000_000:raise HTTPException(422,"Word正文过大，请拆分文件")
            with z.open(info) as stream:
                raw=stream.read(8_000_001)
            if len(raw)>8_000_000:raise HTTPException(422,"Word正文过大")
        root=ET.fromstring(raw)
    except (OSError,KeyError,zipfile.BadZipFile,ParseError,DefusedXmlException):
        raise HTTPException(422,"Word文档损坏或包含不支持的XML")
    body=root.find(W+"body")
    if body is None:raise HTTPException(422,"Word正文不存在")
    def walk(node,depth=0):
        if depth>64:raise HTTPException(422,"Word结构嵌套过深")
        tag=node.tag
        if tag in (M+"oMath",M+"oMathPara"):
            try:
                value=latex(node)
                if not value.strip():raise ValueError("empty")
                return "$"+value+"$"
            except ValueError:
                warnings.add("包含无法无损转换的Word公式，已标记待核对")
                return "[Word公式待核对]"
        if tag in (W+"drawing",W+"pict",W+"object"):
            warnings.add("图片或嵌入对象需查看原文件")
            return "[图形或嵌入对象待核对]"
        if tag==W+"t":return node.text or ""
        if tag==W+"tab":return "\t"
        if tag in (W+"br",W+"cr"):return "\n"
        if tag in (W+"del",W+"pPr",W+"rPr"):return ""
        if tag in (W+"footnoteReference",W+"endnoteReference"):
            warnings.add("脚注及尾注未导入")
            return "[注释待核对]"
        if tag==W+"tbl":
            return "\n".join(" | ".join(walk(cell,depth+1).strip() for cell in row.findall(W+"tc")) for row in node.findall(W+"tr"))
        content="".join(walk(c,depth+1) for c in node)
        return content+"\n" if tag==W+"p" else content
    blocks=[]
    for node in body:
        if node.tag in (W+"p",W+"tbl",W+"sdt"):
            value=walk(node).strip()
            if value:blocks.append(value)
    warnings.add("Word仅提取正文、表格及部分原生公式；页眉页脚、版式、复杂公式请对照原件")
    return blocks,sorted(warnings)

def bounded_command(args,timeout,output=None):
    limiter=shutil.which("prlimit")
    if not limiter or not args[0]:raise HTTPException(503,"本地识别组件未安装")
    try:
        result=subprocess.run([limiter,"--as=805306368","--cpu=18","--fsize=25000000","--",*args],
            stdin=subprocess.DEVNULL,stdout=output if output is not None else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,timeout=timeout,check=False)
        if result.returncode:raise HTTPException(422,"本地识别失败，请检查文件、页码或图片分辨率")
    except (OSError,subprocess.TimeoutExpired):
        raise HTTPException(422,"本地识别超时或无法启动")

def ocr(path,pdf,page):
    cap=capabilities()
    if not cap["pdf_ocr" if pdf else "image_ocr"]:
        raise HTTPException(503,"服务器缺少OCR组件或中英文字库；可先手工粘贴原文")
    with tempfile.TemporaryDirectory(prefix="jiaoyan-ocr-") as tmp:
        if pdf:
            prefix=str(Path(tmp)/"page")
            bounded_command([shutil.which("pdftoppm"),"-f",str(page),"-l",str(page),"-singlefile","-scale-to","2500","-png",str(path),prefix],12)
            path=Path(prefix+".png")
            if not path.is_file():raise HTTPException(422,"PDF页码不存在")
        with tempfile.TemporaryFile() as output:
            bounded_command([shutil.which("tesseract"),str(path),"stdout","-l","chi_sim+eng","--psm","3"],20,output)
            output.seek(0)
            return output.read(262145).decode("utf-8",errors="replace").strip()

def extract(file,mode,start,end):
    if file.archived:raise HTTPException(422,"文件已归档")
    if not 1<=start<=end<=10000:raise HTTPException(422,"范围无效")
    path=storage.file_path(file)
    media=file.media_type
    warnings=[]
    total=None
    if media in TEXT and mode=="text":
        if (start,end)!=(1,1):raise HTTPException(422,"文本无需页码")
        if file.size_bytes>120000:raise HTTPException(422,"文本过大，请拆分")
        try:text=path.read_text(encoding="utf-8-sig").strip()
        except (OSError,UnicodeError):raise HTTPException(422,"仅支持UTF-8文本")
        method="text"
    elif media==DOCX and mode=="text":
        if end-start>=100:raise HTTPException(422,"每批最多100个Word正文段落或表格")
        blocks,warnings=docx_blocks(path)
        total=len(blocks)
        if start>total:raise HTTPException(422,"起始段落超出文档范围")
        end=min(end,total)
        text="\n\n".join(blocks[start-1:end]);method="docx"
    elif media=="application/pdf" and mode=="text":
        text=extract_pdf(file,start,end);method="pdf_text"
        warnings=["PDF文字层可能丢失公式、图形和阅读顺序，必须核对原页；混合扫描页请另选OCR"]
    elif mode=="ocr" and (media=="application/pdf" or media in storage.IMAGE_TYPES):
        if start!=end or (media!="application/pdf" and start!=1):raise HTTPException(422,"OCR每次只识别一张图片或一页PDF")
        text=ocr(path,media=="application/pdf",start);method="pdf_ocr" if media=="application/pdf" else "image_ocr"
        warnings=["OCR仅识别文字，数学公式、上下标、图形和表格可能失真；逐项对照原件，不得当成已核验答案"]
    else:raise HTTPException(415,"此文件格式不支持所选提取方式")
    if not text.strip():raise HTTPException(422,"未提取到文字，请改用OCR或手动录入")
    if len(text)>MAX_TEXT or "\x00" in text:raise HTTPException(422,"每批最多24000字，请缩小范围")
    return {"text":text,"method":method,"start":start,"end":end,"total_units":total,"warnings":warnings}
