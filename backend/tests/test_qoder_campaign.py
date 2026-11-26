from datetime import datetime,timedelta
import pytest
from app.services import qoder_campaign as q

def row(now, state="CLAIMABLE", cid="daily-1"):
    start,end=q.round_window(now)
    return {"campaignId":cid,"actionType":"CLAIM_BENEFIT","claimStatus":state,
            "startAt":int(start.timestamp()*1000),"endAt":int(end.timestamp()*1000),
            "benefit":{"kind":"CREDITS","amount":100}}

def test_beijing_round_boundary():
    now=datetime(2026,11,26,9,59,tzinfo=q.CN)
    assert q.round_window(now)[0].date().isoformat()=="2026-11-25"
    assert q.round_window(now+timedelta(minutes=1))[0].date().isoformat()=="2026-11-26"

def test_campaign_selection_never_claims_other_rewards():
    now=datetime.now(q.CN)
    daily=row(now)
    other=row(now,cid="other")
    other["benefit"]={"kind":"CREDITS","amount":500}
    assert q.select_campaign({"campaigns":[daily,other]},now)==daily
    with pytest.raises(q.CampaignError,match="ambiguous_campaign"):
        q.select_campaign([daily,row(now,cid="duplicate")],now)
    with pytest.raises(q.CampaignError,match="no_verified_campaign"):
        q.select_campaign([row(now-timedelta(days=1))],now)

def test_already_claimed_no_mutation(monkeypatch):
    now=datetime.now(q.CN)
    monkeypatch.setattr(q,"read_pat",lambda:"dummy")
    monkeypatch.setattr(q,"exchange",lambda pat:"test-token")
    def call(path,*,body=None,token=None):
        assert body is None
        return [row(now,"CLAIMED")]
    monkeypatch.setattr(q,"call",call)
    assert q.run_claim(now)=={"state":"already_claimed","earned":None}

def test_claim_verified_by_readback(monkeypatch):
    now=datetime.now(q.CN)
    monkeypatch.setattr(q,"read_pat",lambda:"dummy")
    monkeypatch.setattr(q,"exchange",lambda pat:"test-token")
    calls=[]
    def call(path,*,body=None,token=None):
        calls.append(path)
        if body is not None:return {"status":"CLAIMED","replayed":False,"benefit":{"kind":"CREDITS","amount":100}}
        return [row(now,"CLAIMED" if len(calls)>1 else "CLAIMABLE")]
    monkeypatch.setattr(q,"call",call)
    assert q.run_claim(now)=={"state":"claimed","earned":100}
    assert len(calls)==3

def test_rejected_campaign_is_not_success(monkeypatch):
    now=datetime.now(q.CN)
    monkeypatch.setattr(q,"read_pat",lambda:"dummy")
    monkeypatch.setattr(q,"exchange",lambda pat:"test-token")
    monkeypatch.setattr(q,"call",lambda path,**kw: [row(now,"INELIGIBLE")])
    with pytest.raises(q.CampaignError,match="not_claimable"):
        q.run_claim(now)
