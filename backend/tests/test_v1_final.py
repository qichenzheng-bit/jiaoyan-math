from app.core.config import settings
def test_v1_and_upload_limit():
    assert settings.version == "V1"
    assert settings.max_file_bytes == 200 * 1024 * 1024

def test_original_progress_filter_before_pagination(monkeypatch):
    from unittest.mock import Mock
    from app.api import workspaces
    db=Mock()
    db.scalars.return_value.partitions.return_value=iter([[{"complete":False} for _ in range(100)],[{"complete":True,"id":"match"}]])
    monkeypatch.setattr(workspaces,"library_details",lambda db,part:(part,{},{}))
    result=workspaces.library(q="",archived=False,offset=0,limit=50,db=db,progress_filter="done")
    assert result=={"items":[{"complete":True,"id":"match"}],"total":1}
