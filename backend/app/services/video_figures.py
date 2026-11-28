"""Transfer only authenticated, stored inline question images, in source order."""
import base64
from fastapi import HTTPException
from app.models import StoredFile
from app.services import storage
from app.services.inline_images import IMAGE_TOKEN

FIELDS=("problem","reference_solution","answer","analysis")
MAX_FIGURES=8
MAX_BYTES=8*1024*1024

def prepare(data):
    ids=[]
    normalized=dict(data)
    def replace(match):
        ident=match.group(1)
        if ident not in ids:
            ids.append(ident)
        return f"[参考附图{ids.index(ident)+1}]"
    for field in FIELDS:
        text=IMAGE_TOKEN.sub(replace,data.get(field) or "")
        if "[[img:" in text or "![" in text:
            raise HTTPException(422,"请使用题库内嵌图片功能，不支持外部图片链接")
        normalized[field]=text
    if len(ids)>MAX_FIGURES:
        raise HTTPException(422,"单个视频题目最多传输8张参考图")
    return normalized,ids

def payload(db,ids):
    if len(ids)>MAX_FIGURES or len(set(ids))!=len(ids):
        raise HTTPException(422,"参考图编号无效")
    figures=[];total=0
    for ident in ids:
        item=db.get(StoredFile,ident)
        if item is None or item.archived or item.media_type not in storage.IMAGE_TYPES:
            raise HTTPException(422,"参考题图不可用，请恢复原图")
        path=storage.file_path(item)
        size=path.stat().st_size
        total+=size
        if total>MAX_BYTES or not size:
            raise HTTPException(422,"视频参考图合计不得超过8 MiB，请优化原图")
        raw=path.read_bytes()
        if len(raw)!=size:
            raise HTTPException(409,"参考图已变化，请重试")
        figures.append({"media_type":item.media_type,"base64":base64.b64encode(raw).decode("ascii")})
    return figures
