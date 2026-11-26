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


def test_save_pat_verifies_before_writing_and_keeps_secret_private(tmp_path,monkeypatch):
    path=tmp_path/"qoder-checkin.pat"
    monkeypatch.setattr(q,"PAT_FILE",path)
    monkeypatch.setattr(q,"exchange",lambda pat:"short-lived-token")
    q.save_pat("pt-example-valid-token")
    assert q.read_pat()=="pt-example-valid-token"
    assert path.stat().st_mode & 0o777 == 0o600
    def reject(pat):
        raise q.CampaignError("authorization_denied")
    monkeypatch.setattr(q,"exchange",reject)
    with pytest.raises(q.CampaignError,match="authorization_denied"):
        q.save_pat("pt-another-valid-token")
    assert q.read_pat()=="pt-example-valid-token"

def test_quota_snapshot_rejects_missing_values(monkeypatch):
    monkeypatch.setattr(q,"read_pat",lambda:"dummy")
    monkeypatch.setattr(q,"exchange",lambda pat:"token")
    monkeypatch.setattr(q,"call",lambda *a,**kw:{"userQuota":{"remaining":100},"addOnQuota":{"used":10}})
    with pytest.raises(q.CampaignError,match="unexpected_response"):
        q.quota_snapshot()

def test_observed_balance_ledger_has_signed_deltas_and_no_first_snapshot_gain():
    from app.api.qiandao import apply_snapshot
    at=int(datetime(2026,11,26,10,tzinfo=q.CN).timestamp())
    state={}
    def snap(offset,balance,kind="userQuota"):
        return {"at":at+offset,"balance":balance,"packs":[{"kind":kind}]}
    apply_snapshot(state,snap(0,500))
    assert not state.get("changes")
    apply_snapshot(state,snap(60,600))
    apply_snapshot(state,snap(120,580))
    assert [r["delta"] for r in state["changes"]]==[-20,100]
    assert state["daily"]["increase"]==100
    assert state["daily"]["decrease"]==20
    apply_snapshot(state,snap(180,1000,"other"))
    assert len(state["changes"])==2
