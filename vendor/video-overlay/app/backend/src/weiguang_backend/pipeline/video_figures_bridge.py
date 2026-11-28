"""Bounded transfer of immutable question figures to the independent engine.

No model-supplied path or remote URL is accepted. The CLI receives an actual
image attachment; generated Manim code never accesses these files.
"""
from __future__ import annotations
import base64
import hashlib
import io
import math
from pathlib import Path
from PIL import Image, ImageDraw
MAX_BYTES=8*1024*1024
MAX_FIGURES=8
MAX_PIXELS=24_000_000
FORMATS={"image/png":("PNG",".png"),"image/jpeg":("JPEG",".jpg"),
         "image/webp":("WEBP",".webp"),"image/gif":("GIF",".gif")}

def decode(payload):
    if not isinstance(payload,list) or not 0<len(payload)<=MAX_FIGURES:
        raise ValueError("VIDEO_FIGURE_COUNT_INVALID")
    result=[];total=0;pixels=0
    for item in payload:
        if not isinstance(item,dict) or set(item)!={"media_type","base64"}:
            raise ValueError("VIDEO_FIGURE_INVALID")
        media=item["media_type"];encoded=item["base64"]
        if media not in FORMATS or not isinstance(encoded,str) or len(encoded)>4*((MAX_BYTES+2)//3):
            raise ValueError("VIDEO_FIGURE_INVALID")
        raw=base64.b64decode(encoded,validate=True)
        total+=len(raw)
        if not raw or total>MAX_BYTES:
            raise ValueError("VIDEO_FIGURE_TOO_LARGE")
        try:
            with Image.open(io.BytesIO(raw)) as im:
                pixels+=im.width*im.height
                if im.format!=FORMATS[media][0] or pixels>MAX_PIXELS:
                    raise ValueError("VIDEO_FIGURE_FORMAT_OR_SIZE")
                im.verify()
        except Exception as exc:
            raise ValueError("VIDEO_FIGURE_INVALID") from exc
        result.append((media,raw))
    return result

def store(root,figures):
    """Content-addressed copies, retained with the engine lesson."""
    folder=Path(root)/"reference_figures"
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    refs=[]
    for i,(media,raw) in enumerate(figures,1):
        digest=hashlib.sha256(raw).hexdigest()
        path=folder/(f"{i:02d}-"+digest+FORMATS[media][1])
        if not path.exists():
            path.write_bytes(raw)
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError("VIDEO_FIGURE_DIGEST_MISMATCH")
        refs.append({"path":str(path),"index":i-1,"field":"problem","caption":f"参考附图{i}","sha256":digest})
    return refs

def cli_attachment(paths):
    """Use the existing single-image Qoder CLI attachment interface.
    Multiple images are arranged in a numbered, lossless contact sheet, no scaling.
    """
    if not 0<len(paths)<=MAX_FIGURES:
        raise ValueError("VIDEO_FIGURE_COUNT_INVALID")
    items=[]
    for path in paths:
        raw=Path(path).read_bytes()
        if len(raw)>MAX_BYTES:raise ValueError("VIDEO_FIGURE_TOO_LARGE")
        with Image.open(io.BytesIO(raw)) as im:
            media=next((k for k,v in FORMATS.items() if v[0]==im.format),None)
        if not media:raise ValueError("VIDEO_FIGURE_INVALID")
        items.append({"media_type":media,"base64":base64.b64encode(raw).decode("ascii")})
    figures=decode(items)
    if len(figures)==1:return items[0]
    images=[]
    for _,raw in figures:
        with Image.open(io.BytesIO(raw)) as im:
            rgba=im.convert("RGBA")
            bg=Image.new("RGB",rgba.size,"white")
            bg.paste(rgba,mask=rgba.getchannel("A"))
            images.append(bg)
    # Two columns max; each cell sized to its content, with numbered label.
    cols=min(2,len(images));rows=math.ceil(len(images)/cols)
    widths=[max(images[i].width for i in range(c,len(images),cols))+32 for c in range(cols)]
    heights=[max(im.height for im in images[j*cols:(j+1)*cols])+64 for j in range(rows)]
    if sum(widths)*sum(heights)>MAX_PIXELS:raise ValueError("VIDEO_FIGURE_CONTACT_SHEET_TOO_LARGE")
    canvas=Image.new("RGB",(sum(widths),sum(heights)),"white")
    draw=ImageDraw.Draw(canvas)
    for i,im in enumerate(images):
        row,col=divmod(i,cols)
        x,y=sum(widths[:col]),sum(heights[:row])
        draw.rectangle((x+2,y+2,x+widths[col]-3,y+heights[row]-3),outline="#777777",width=2)
        draw.text((x+16,y+12),f"Figure {i+1}",fill="black")
        canvas.paste(im,(x+16,y+40))
    output=io.BytesIO();canvas.save(output,format="PNG",optimize=True)
    raw=output.getvalue()
    if len(raw)>MAX_BYTES:raise ValueError("VIDEO_FIGURE_CONTACT_SHEET_TOO_LARGE")
    return {"media_type":"image/png","base64":base64.b64encode(raw).decode("ascii")}
