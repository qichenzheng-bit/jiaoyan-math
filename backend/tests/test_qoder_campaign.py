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


def test_empty_activity_list_is_not_account_ineligibility():
    with pytest.raises(q.CampaignError,match="campaigns_not_returned") as exc:
        q.select_campaign({"campaigns":[]})
    assert exc.value.retry

def test_daily_activity_with_small_time_offset():
    now=datetime(2026,11,26,12,tzinfo=q.CN)
    activity=row(now)
    activity["startAt"]+=120000
    activity["endAt"]-=120000
    assert q.select_campaign([activity],now)==activity

def test_known_daily_campaign_can_have_shorter_active_window():
    now=datetime(2026,11,26,12,tzinfo=q.CN)
    activity=row(now)
    activity["campaignKey"]="cn_daily_check_in_legacy"
    activity["endAt"]-=3600000
    assert q.select_campaign([activity],now)==activity

def test_campaign_request_has_routing_parameter_without_fake_device(monkeypatch):
    import io
    class Opener:
        def open(self, req, timeout):
            headers={k.lower():v for k,v in req.header_items()}
            assert headers["cosy-clienttype"]=="10"
            assert headers["user-agent"]=="JiaoyanMath-QoderCheckin/1"
            assert not any(k.startswith("cosy-machine") for k in headers)
            return io.BytesIO(b'{"data":{"campaigns":[]}}')
    monkeypatch.setattr(q,"build_opener",lambda *args:Opener())
    assert q.call("/sash/api/v1/me/campaigns",token="test")=={"campaigns":[]}


def test_confirmed_reward_is_recovered_from_existing_history_not_balance():
    from app.api.qiandao import confirmed_rewards
    state={"history":[
        {"round":"2026-11-26","state":"claimed","earned":100,"at":1795660000},
        {"round":"2026-11-26","state":"claimed","earned":100,"at":1795660001},
        {"round":"2026-11-25","state":"already_claimed","earned":None,"at":1795573600},
        {"round":"2026-11-24","state":"claimed","earned":None,"at":1795487200},
    ],"changes":[]}
    assert confirmed_rewards(state)==[{"round":"2026-11-26","at":1795660000,"delta":100}]

def test_claim_samples_balance_before_and_after_and_preserves_confirmed_reward(monkeypatch):
    from app.api import qiandao
    import copy
    stored={"enabled":True,"history":[]}
    def read(db):return copy.deepcopy(stored)
    def write(db,state):
        stored.clear()
        stored.update(copy.deepcopy(state))
    monkeypatch.setattr(qiandao,"read_state",read)
    monkeypatch.setattr(qiandao,"write_state",write)
    monkeypatch.setattr(qiandao,"view",read)
    calls=[]
    def quota():
        calls.append("quota")
        return {"at":1795660000+len(calls),"balance":3553,"packs":[{"kind":"userQuota"}]}
    def claim():
        calls.append("claim")
        return {"state":"claimed","earned":100}
    monkeypatch.setattr(q,"quota_snapshot",quota)
    monkeypatch.setattr(q,"run_claim",claim)
    result=qiandao.attempt(None,manual=True)
    assert calls==["quota","claim","quota"]
    assert result["quota"]["balance"]==3553
    assert result["daily"]["increase"]==0
    assert qiandao.confirmed_rewards(result)[0]["delta"]==100
    qiandao.attempt(None,manual=True)
    assert calls==["quota","claim","quota"]

def test_quota_source_change_does_not_create_false_gain():
    from app.api.qiandao import apply_snapshot
    state={}
    for at,source,balance in [(1795660000,"one",3553),(1795660001,"two",3653)]:
        apply_snapshot(state,{"at":at,"balance":balance,"source":source,"packs":[{"kind":"userQuota"}]})
    assert not state.get("changes")
