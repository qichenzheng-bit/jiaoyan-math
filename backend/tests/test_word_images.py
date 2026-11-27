import zipfile
from types import SimpleNamespace
from app.services import word_images as wi, material_vision as vision, material_import as imp
from fastapi import HTTPException

def document(tmp_path):
    path=tmp_path/"mixed.docx"
    xml="""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>
    <w:p><w:r><w:t>前段</w:t></w:r></w:p>
    <w:p><w:r><w:t>求</w:t><w:drawing><a:blip r:embed="rId1"/></w:drawing><w:t>的值</w:t></w:r><m:oMath><m:f><m:num><m:r><m:t>1</m:t></m:r></m:num><m:den><m:r><m:t>x</m:t></m:r></m:den></m:f></m:oMath></w:p>
    <w:p><w:r><w:drawing><a:blip r:link="rId2"/></w:drawing></w:r></w:p>
    <w:p><w:r><w:drawing><a:blip r:embed="rId3"/></w:drawing></w:r></w:p>
    </w:body></w:document>"""
    rels="""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="https://example.org/private.png" TargetMode="External"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../secret.png"/></Relationships>"""
    with zipfile.ZipFile(path,"w") as z:
        z.writestr("word/document.xml",xml)
        z.writestr("word/_rels/document.xml.rels",rels)
        z.writestr("word/media/image1.png",b"\x89PNG\r\n\x1a\nexample")
        z.writestr("secret.png",b"\x89PNG\r\n\x1a\nsecret")
    return path

def test_embedded_image_order_and_stable_block_numbers(tmp_path):
    path=document(tmp_path)
    seen=[]
    def handler(i,media,raw):
        seen.append((i,media,raw))
        return "$x^2$"
    result=wi.block(path,2,handler)
    assert result["text"]==r"求$x^2$的值$\frac{1}{x}$"
    assert result["total_units"]==len(imp.docx_blocks(path)[0])==4
    assert seen==[(1,"image/png",b"\x89PNG\r\n\x1a\nexample")]
    assert wi.block(path,1,handler)["text"]=="前段"
    assert len(seen)==1

def test_external_and_traversal_images_are_never_read(tmp_path):
    path=document(tmp_path)
    def handler(*args):raise AssertionError("external attachment must not be loaded")
    for unit in (3,4):
        result=wi.block(path,unit,handler)
        assert "[Word图片1待核对]" in result["text"]
        assert any("外部或缺失" in w for w in result["warnings"])

def test_word_uses_vision_only_for_embedded_images(tmp_path,monkeypatch):
    path=document(tmp_path)
    monkeypatch.setattr(vision.storage,"file_path",lambda f:path)
    calls=[]
    def recognize(media,raw,model,effort,timeout):
        calls.append((media,model))
        return {"text":"$x^2$","method":"qoder_vision","warnings":[]}
    monkeypatch.setattr(vision,"recognize_bytes",recognize)
    f=SimpleNamespace(media_type=imp.DOCX)
    assert vision.word_step(f,1,{},"DeepSeek-Flash")["method"]=="docx"
    result=vision.word_step(f,2,{},"DeepSeek-Flash")
    assert result["method"]=="docx_vision" and result["state"]=="done"
    assert result["text"]==r"求$x^2$的值$\frac{1}{x}$"
    assert calls==[("image/png","DeepSeek-Flash")]

def many_images(tmp_path,count):
    path=tmp_path/"many.docx"
    images="".join(f'<w:r><w:t>{i}:</w:t><w:drawing><a:blip r:embed="rId{i}"/></w:drawing></w:r>' for i in range(1,count+1))
    xml='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p>'+images+'</w:p></w:body></w:document>'
    rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image{i}.png"/>' for i in range(1,count+1))+'</Relationships>'
    with zipfile.ZipFile(path,"w") as z:
        z.writestr("word/document.xml",xml)
        z.writestr("word/_rels/document.xml.rels",rels)
        for i in range(1,count+1):
            z.writestr(f"word/media/image{i}.png",b"\x89PNG\r\n\x1a\n"+str(i).encode())
    return path

def test_word_image_queue_has_no_four_image_limit_and_resumes(tmp_path,monkeypatch):
    import json
    path=many_images(tmp_path,17)
    monkeypatch.setattr(vision.storage,"file_path",lambda f:path)
    f=SimpleNamespace(media_type=imp.DOCX)
    calls=[]
    def recognize(media,raw,model,effort,timeout):
        n=int(raw[8:])
        calls.append(n)
        if n==9 and calls.count(9)==1:raise HTTPException(503,"temporary failure")
        return {"text":f"$x_{{{n}}}$","method":"qoder_vision","warnings":[]}
    monkeypatch.setattr(vision,"recognize_bytes",recognize)
    saved={}
    for i in range(8):
        saved=vision.word_step(f,1,json.loads(json.dumps(saved)),"DeepSeek-Flash")
        assert saved["state"]=="partial"
        assert saved["image_total"]==17
        assert saved["image_completed"]==i+1
    saved=vision.word_step(f,1,saved,"DeepSeek-Flash")
    assert saved["state"]=="failed" and saved["image_current"]==9
    assert saved["image_completed"]==8 and "temporary failure" in saved["error"]
    for i in range(9,18):
        saved=vision.word_step(f,1,json.loads(json.dumps(saved)),"DeepSeek-Flash")
        assert saved["image_completed"]==i
    assert saved["state"]=="done"
    assert saved["text"]=="".join(f"{i}:$x_{{{i}}}$" for i in range(1,18))
    assert calls==list(range(1,10))+list(range(9,18))

def test_failed_image_can_be_retried_with_ai_or_explicitly_deferred(tmp_path,monkeypatch):
    path=many_images(tmp_path,3)
    monkeypatch.setattr(vision.storage,"file_path",lambda f:path)
    f=SimpleNamespace(media_type=imp.DOCX)
    def recognize(media,raw,*args):
        if raw.endswith(b"2"):raise HTTPException(422,"vision failed")
        return {"text":"formula","method":"qoder_vision","warnings":[]}
    monkeypatch.setattr(vision,"recognize_bytes",recognize)
    first=vision.word_step(f,1,{},"Auto")
    failed=vision.word_step(f,1,first,"Auto")
    assert failed["state"]=="failed" and failed["image_completed"]==1
    retried=vision.word_step(f,1,failed)
    assert retried["state"]=="failed" and retried["image_completed"]==1
    deferred=vision.word_step(f,1,failed,manual_review=True)
    assert deferred["state"]=="partial" and deferred["image_review"]==1
    done=vision.word_step(f,1,deferred,"Auto")
    assert done["state"]=="done" and done["image_completed"]==2
    assert done["text"]=="1:formula2:[Word图片2待核对]3:formula"
    assert any("明确交由人工核对" in w for w in done["warnings"])

def test_preview_metadata_does_not_read_all_image_bytes(tmp_path,monkeypatch):
    path=many_images(tmp_path,15)
    original=wi.read_image
    calls=[]
    def read(z,rels,rid):
        calls.append(rid)
        return original(z,rels,rid)
    monkeypatch.setattr(wi,"read_image",read)
    def handler(index,media,loader):
        assert media=="image/png"
        if index==15:assert loader()[1].endswith(b"15")
        return f"[Word原图{index}]"
    result=wi.scan(path,1,handler)
    assert result["image_total"]==15 and calls==["rId15"]
