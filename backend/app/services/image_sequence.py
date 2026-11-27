"""Treat one multi-image upload as an ordered PDF, keeping the raw uploads intact."""
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import HTTPException
from app.models import StoredFile
from app.services import storage

def create_sequence(db,ids,user_id):
    pages=[]
    stage=storage.new_stage()
    try:
        for fid in ids:
            f=db.get(StoredFile,fid)
            if not f or f.archived or f.generated or f.media_type not in storage.IMAGE_TYPES:
                raise HTTPException(422,"连续图片资料必须全部为有效原图")
            with Image.open(storage.file_path(f)) as original:
                if original.width*original.height>40_000_000:
                    raise HTTPException(422,"单张图片像素过大，请缩小后上传")
                image=ImageOps.exif_transpose(original)
                image.thumbnail((2500,2500),Image.Resampling.LANCZOS)
                rgba=image.convert("RGBA")
                page=Image.new("RGB",rgba.size,"white")
                page.paste(rgba,mask=rgba.getchannel("A"))
                pages.append(page)
        pages[0].save(stage,format="PDF",save_all=True,append_images=pages[1:],resolution=150,quality=95)
        return storage.save_staged(db,stage,"连续图片资料.pdf",user_id)["id"]
    except (OSError,ValueError,UnidentifiedImageError,Image.DecompressionBombError):
        raise HTTPException(422,"连续图片无法合并，请检查原图")
    finally:
        for page in pages:page.close()
        stage.unlink(missing_ok=True)
