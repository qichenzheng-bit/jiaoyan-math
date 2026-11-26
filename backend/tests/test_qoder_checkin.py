from datetime import datetime,timezone
from app.api.studio import qoder_round

def test_claim_round_respects_beijing_10am():
    assert qoder_round(datetime(2026,11,26,1,59,tzinfo=timezone.utc))=="2026-11-25"
    assert qoder_round(datetime(2026,11,26,2,0,tzinfo=timezone.utc))=="2026-11-26"
