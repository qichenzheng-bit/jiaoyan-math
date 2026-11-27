import pytest
from fastapi import HTTPException
from app.api.documents import COMPLETE_EXPORT_MAX_BYTES,check_complete_export_size

def test_complete_export_200_mb_boundary():
    assert COMPLETE_EXPORT_MAX_BYTES==200_000_000
    check_complete_export_size(COMPLETE_EXPORT_MAX_BYTES-1)
    check_complete_export_size(COMPLETE_EXPORT_MAX_BYTES)
    with pytest.raises(HTTPException) as exc:
        check_complete_export_size(COMPLETE_EXPORT_MAX_BYTES+1)
    assert exc.value.status_code==422
