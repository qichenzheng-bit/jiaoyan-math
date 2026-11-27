"""Conservative three-way merge. Never resolves conflicting edits silently."""
class MergeConflict(ValueError):
    pass

def choose(base, local, remote, label):
    if local==remote:return local
    if local==base:return remote
    if remote==base:return local
    raise MergeConflict(label)

def merge_document(base,local,remote):
    result={k:choose(base.get(k),local.get(k),remote.get(k),k) for k in ("title","kind","subject","source_id")}
    versions=[{b["uid"]:b for b in doc["blocks"]} for doc in (base,local,remote)]
    orders=[[b["uid"] for b in doc["blocks"]] for doc in (base,local,remote)]
    order=choose(*orders,"内容增删或排序")
    merged=[]
    for uid in order:
        b,l,r=(v.get(uid) for v in versions)
        if b is None or l is None or r is None:
            merged.append(choose(b,l,r,"条目 "+uid));continue
        # Type/resource replacement, structured questions and score components are atomic groups.
        groups=[("kind","resource_id","file_id"),("score","subquestion_scores")]
        if b.get("kind")=="question":groups.append(("content","answer","solution","question_type","question_data"))
        if any(v.get("kind")!=b.get("kind") or v.get("resource_id")!=b.get("resource_id") for v in (l,r)):
            merged.append(choose(b,l,r,"替换条目 "+uid));continue
        out={"uid":uid}
        grouped={k for group in groups for k in group}
        for group in groups:
            values=[{k:v.get(k) for k in group} for v in (b,l,r)]
            out.update(choose(*values,"条目 "+uid+" / "+"/".join(group)))
        for key in (set(b)|set(l)|set(r))-grouped-{"uid"}:
            out[key]=choose(b.get(key),l.get(key),r.get(key),"条目 "+uid+" / "+key)
        merged.append(out)
    # Do not drop edits made to blocks deleted by the other device.
    for uid in set(orders[0])-set(order):
        b,l,r=(v.get(uid) for v in versions)
        choose(b,l,r,"删除条目 "+uid)
    result["blocks"]=merged
    return result
