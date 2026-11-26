"""Qoder CN campaign adapter. Explicitly configured PAT only; no client/device impersonation."""
import json
import math
import os
import re
import stat
import time
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

BASE = "https://openapi.qoder.com.cn"
CN = timezone(timedelta(hours=8))
PAT_FILE = Path.home() / "jiaoyan-app/config/qoder-checkin.pat"

class CampaignError(Exception):
    def __init__(self, code, retry=False):
        super().__init__(code)
        self.code = code
        self.retry = retry

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def read_pat():
    # Separate from CLI auth; never send the secret to the browser or database.
    try:
        fd = os.open(PAT_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise CampaignError("pat_permissions")
            value = f.read(4097).decode("utf-8").strip()
    except CampaignError:
        raise
    except (OSError, UnicodeError):
        raise CampaignError("pat_missing") from None
    if not re.fullmatch(r"pt-[A-Za-z0-9._-]{8,4090}", value):
        raise CampaignError("pat_invalid")
    return value

def call(path, *, body=None, token=None):
    headers = {"Accept":"application/json","User-Agent":"JiaoyanMath-QoderCheckin/1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    raw = None if body is None else json.dumps(body).encode()
    if raw is not None:
        headers["Content-Type"] = "application/json"
    request = Request(BASE+path, data=raw, headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as res:
            data = json.loads(res.read(524289))
    except HTTPError as exc:
        if exc.code in (401,403):
            raise CampaignError("authorization_denied") from None
        if exc.code == 429:
            raise CampaignError("rate_limited", True) from None
        if exc.code >= 500:
            raise CampaignError("upstream_unavailable", True) from None
        raise CampaignError("endpoint_unavailable") from None
    except (OSError, URLError, ValueError):
        raise CampaignError("upstream_unavailable", True) from None
    if isinstance(data, dict) and data.get("success") is False:
        raise CampaignError("upstream_rejected")
    return data.get("data", data) if isinstance(data, dict) else data

def exchange(pat):
    data = call("/api/v1/jobToken/exchange", body={"personal_token":pat})
    token = data.get("token") if isinstance(data,dict) else None
    if not isinstance(token,str) or not token or len(token)>8192:
        raise CampaignError("authorization_denied")
    return token

def round_window(now=None):
    now = datetime.now(CN) if now is None else now.astimezone(CN)
    start = (now-timedelta(hours=10)).replace(hour=10,minute=0,second=0,microsecond=0)
    return start, start+timedelta(days=1)

def stamp(value):
    if isinstance(value,bool):
        return None
    try:
        v=float(value)
        if not math.isfinite(v): return None
        return v/1000 if v>1e12 else v
    except (TypeError,ValueError,OverflowError):
        return None

def select_campaign(payload, now=None):
    """Only the unambiguous current daily 100-credit reward, never unrelated promotions."""
    now = datetime.now(CN) if now is None else now.astimezone(CN)
    start,end=round_window(now)
    rows=payload.get("campaigns") if isinstance(payload,dict) else payload
    if not isinstance(rows,list):
        raise CampaignError("unexpected_response")
    candidates=[]
    for row in rows:
        if not isinstance(row,dict) or str(row.get("actionType","")).upper()!="CLAIM_BENEFIT":
            continue
        benefit=row.get("benefit")
        if not isinstance(benefit,dict) or str(benefit.get("kind","")).upper()!="CREDITS" or stamp(benefit.get("amount"))!=100:
            continue
        begin,finish=stamp(row.get("startAt")),stamp(row.get("endAt"))
        if begin is None or finish is None:
            continue
        if abs(begin-start.timestamp())>1 or abs(finish-end.timestamp())>1:
            continue
        if not begin<=now.timestamp()<finish:
            continue
        ident=row.get("campaignId")
        if not isinstance(ident,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}",ident):
            continue
        candidates.append(row)
    if len(candidates)>1:
        raise CampaignError("ambiguous_campaign")
    if not candidates:
        raise CampaignError("no_verified_campaign")
    return candidates[0]

def run_claim(now=None, *, claim=True):
    """Query before claiming. Confirm with a fresh query; never infer from quota changes."""
    now=datetime.now(CN) if now is None else now.astimezone(CN)
    token=exchange(read_pat())
    path="/sash/api/v1/me/campaigns"
    row=select_campaign(call(path,token=token),now)
    state=str(row.get("claimStatus","")).upper()
    if state=="CLAIMED":
        return {"state":"already_claimed","earned":None}
    if state!="CLAIMABLE":
        raise CampaignError("not_claimable")
    if not claim:
        return {"state":"claimable","earned":None}
    result=call(path+"/"+row["campaignId"]+"/claim",body={},token=token)
    if not isinstance(result,dict):
        raise CampaignError("claim_unconfirmed",True)
    checked=select_campaign(call(path,token=token))
    if checked["campaignId"]!=row["campaignId"] or str(checked.get("claimStatus","")).upper()!="CLAIMED":
        raise CampaignError("claim_unconfirmed",True)
    # Only count an actual award explicitly reported by the upstream.
    benefit=result.get("benefit")
    earned=None
    if result.get("replayed") is False and str(result.get("status","")).upper()=="CLAIMED" and isinstance(benefit,dict) and str(benefit.get("kind","")).upper()=="CREDITS" and stamp(benefit.get("amount"))==100:
        earned=100
    return {"state":"claimed","earned":earned}


def save_pat(value):
    value=value.strip()
    if not re.fullmatch(r"pt-[A-Za-z0-9._-]{8,4090}",value):
        raise CampaignError("pat_invalid")
    # Verify authorization without claiming anything.
    exchange(value)
    fd,name=tempfile.mkstemp(prefix=".qoder-checkin.",dir=PAT_FILE.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as handle:
            handle.write(value+"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name,PAT_FILE)
    finally:
        if os.path.exists(name):os.unlink(name)

def quota_snapshot():
    """Read the PAT account's own quota, never combine with unrelated CLI account."""
    token=exchange(read_pat())
    raw=call("/api/v2/quota/usage",token=token)
    if not isinstance(raw,dict):raise CampaignError("unexpected_response")
    def number(v):
        if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0:return float(v)
        return None
    packs=[]
    def add(key,label,row):
        if not isinstance(row,dict) or row.get("available") is False:return
        remaining=number(row.get("remaining",row.get("Remaining")))
        total=number(row.get("total",row.get("Total",row.get("cap"))))
        used=number(row.get("used",row.get("Used")))
        unit=row.get("unit",row.get("Unit"))
        if unit is not None and str(unit).lower() not in ("credit","credits"):raise CampaignError("unexpected_response")
        if remaining is None:raise CampaignError("unexpected_response")
        packs.append({"kind":key,"label":label,"remaining":remaining,"total":total,"used":used})
    for key,label in (("userQuota","套餐额度"),("addOnQuota","加油包"),("orgResourcePackage","共享额度")):
        add(key,label,raw.get(key))
    if not raw.get("orgResourcePackage"):add("sharedQuota","共享额度",raw.get("sharedQuota"))
    dedicated=raw.get("dedicatedResourcePackages",[])
    if not isinstance(dedicated,list):raise CampaignError("unexpected_response")
    for i,item in enumerate(dedicated):add("dedicated:"+str(i),"专用额度",item)
    if not packs:raise CampaignError("unexpected_response")
    return {"balance":round(sum(p["remaining"] for p in packs),6),"packs":packs,"at":int(time.time())}
