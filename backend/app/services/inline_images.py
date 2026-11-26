"""Strict stored image tokens in teaching text. Resize is presentation-only."""
import re
from fastapi import HTTPException
from app.models import StoredFile
from app.services import storage

IMAGE_TOKEN=re.compile(r"\[\[img:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}):(20|25|30|35|40|45|50|55|60|65|70|75|80|85|90|95|100)\]\]")
FIELDS=("title","content","answer","solution","analysis","proof")

def image_ids(data):
    return {match.group(1) for field in FIELDS for match in IMAGE_TOKEN.finditer(data.get(field) or "")}

def validate_images(db,data):
    ids=image_ids(data)
    if len(ids)>80:
        raise HTTPException(422,"单条内容最多插入80张图片")
    for file_id in ids:
        item=db.get(StoredFile,file_id)
        if not item or item.archived or item.media_type not in storage.IMAGE_TYPES:
            raise HTTPException(422,"内嵌图片不存在、已停用或格式无效")
    return ids

def protect_resource_images(db,row):
    # Retain previous versions' referenced images so document snapshots remain readable.
    for file_id in validate_images(db,{k:getattr(row,k,"") for k in FIELDS}):
        storage.link_file(db,file_id,"teaching_resource",row.id)
