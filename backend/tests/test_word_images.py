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
    assert vision.recognize_word(f,1,"DeepSeek-Flash")["method"]=="docx"
    result=vision.recognize_word(f,2,"DeepSeek-Flash")
    assert result["method"]=="docx_vision"
    assert result["text"]==r"求$x^2$的值$\frac{1}{x}$"
    assert calls==[("image/png","DeepSeek-Flash")]

def test_word_failed_image_preserves_native_text_and_marker(tmp_path,monkeypatch):
    path=document(tmp_path)
    monkeypatch.setattr(vision.storage,"file_path",lambda f:path)
    def fail(*args):raise HTTPException(422,"vision failed")
    monkeypatch.setattr(vision,"recognize_bytes",fail)
    result=vision.recognize_word(SimpleNamespace(media_type=imp.DOCX),2,"Auto")
    assert result["method"]=="docx"
    assert result["text"]==r"求[Word图片1待核对]的值$\frac{1}{x}$"
    assert any("vision failed" in w for w in result["warnings"])
