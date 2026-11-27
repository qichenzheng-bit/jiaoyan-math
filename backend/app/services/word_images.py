"""Resolve only embedded Word image relationships; never fetch external targets."""
import posixpath
import zipfile
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError
from fastapi import HTTPException
from app.services import material_import as imp

MAX_IMAGE_BYTES=8*1024*1024
MAX_IMAGES_PER_BLOCK=4
R="{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A="{http://schemas.openxmlformats.org/drawingml/2006/main}"
V="{urn:schemas-microsoft-com:vml}"
REL="{http://schemas.openxmlformats.org/package/2006/relationships}"
MEDIA={".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp",".gif":"image/gif"}

def relationships(z):
    try:
        info=z.getinfo("word/_rels/document.xml.rels")
    except KeyError:
        return {}
    if info.file_size>1_000_000: raise HTTPException(422,"Word图片关系表过大")
    try:
        root=ET.fromstring(z.read(info))
    except (ParseError,DefusedXmlException):
        raise HTTPException(422,"Word图片关系表损坏")
    result={}
    for row in root.findall(REL+"Relationship"):
        if row.get("TargetMode","Internal")!="Internal" or not row.get("Type","").endswith("/image"):continue
        rid,target=row.get("Id"),row.get("Target","")
        if not rid or not target or any(c in target for c in ("\\",":","?","#","%")):continue
        if ".." in target.split("/"):continue
        name=posixpath.normpath(target.lstrip("/") if target.startswith("/") else "word/"+target)
        if name.startswith("word/media/") and not name.endswith("/"):result[rid]=name
    return result

def references(node):
    ids=[]
    for child in node.iter():
        if child.tag==A+"blip":
            ids.append(child.get(R+"embed") or child.get(R+"link"))
        elif child.tag==V+"imagedata":
            ids.append(child.get(R+"id"))
    # Multiple representations of the same embedded image within one drawing.
    return list(dict.fromkeys(ids))

def read_image(z,rels,rid):
    name=rels.get(rid)
    if not name: raise HTTPException(422,"外部或缺失的Word图片引用")
    media=MEDIA.get(posixpath.splitext(name)[1].lower())
    if not media: raise HTTPException(415,"Word内嵌图片格式暂不支持（如EMF、WMF）")
    try:
        info=z.getinfo(name)
        if not 0<info.file_size<=MAX_IMAGE_BYTES:raise HTTPException(422,"Word内嵌图片为空或超过8 MiB")
        with z.open(info) as stream: raw=stream.read(MAX_IMAGE_BYTES+1)
    except (KeyError,OSError,zipfile.BadZipFile,RuntimeError):
        raise HTTPException(422,"Word内嵌图片无法读取")
    valid=(media=="image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n") or media=="image/jpeg" and raw.startswith(b"\xff\xd8\xff") or media=="image/webp" and raw[:4]==b"RIFF" and raw[8:12]==b"WEBP" or media=="image/gif" and raw[:6] in (b"GIF87a",b"GIF89a"))
    if not valid or len(raw)>MAX_IMAGE_BYTES:raise HTTPException(422,"Word内嵌图片内容与格式不符")
    return media,raw

def block(path,unit,handler):
    """Invoke handler for supported images of one stable logical block, in source order."""
    messages=[]
    ordinal=0
    try:
        with zipfile.ZipFile(path) as z:
            rels=relationships(z)
            def drawing(node):
                nonlocal ordinal
                refs=references(node)
                if not refs:
                    messages.append("含无法提取的Word图形或嵌入对象，请查看原件")
                    return "[图形或嵌入对象待核对]"
                parts=[]
                for rid in refs:
                    ordinal+=1
                    marker=f"[Word图片{ordinal}待核对]"
                    if ordinal>MAX_IMAGES_PER_BLOCK:
                        if ordinal==MAX_IMAGES_PER_BLOCK+1: messages.append("本段内嵌图片超过4张，剩余图片请核对原文件")
                        parts.append(marker)
                        continue
                    try: media,raw=read_image(z,rels,rid)
                    except HTTPException as exc:
                        messages.append(f"Word图片{ordinal}：{exc.detail}")
                        parts.append(marker)
                        continue
                    parts.append(handler(ordinal,media,raw))
                return " ".join(parts)
            blocks,warnings=imp.docx_blocks(path,target_unit=unit,image_handler=drawing)
    except (OSError,zipfile.BadZipFile,RuntimeError):
        raise HTTPException(422,"Word文件或图片关系损坏")
    if not 1<=unit<=len(blocks):raise HTTPException(422,"Word段落超出文档范围")
    return {"text":blocks[unit-1],"total_units":len(blocks),"warnings":[w for w in warnings if w!="图片或嵌入对象需查看原文件"]+messages}
