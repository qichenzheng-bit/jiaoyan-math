import re
"""Actual compiled React UI tests with isolated synthetic API responses."""
import os
from pathlib import Path
import json
from playwright.sync_api import sync_playwright, expect
OUT=Path("ui-screenshots");OUT.mkdir(exist_ok=True)
subjects=["高等数学","线性代数","概率论与数理统计","数学分析","高等代数"]
source={"id":"source-preview","code":"SDEMO0001","kind":"source","title":"考研数学（一）示例试卷","subject":"高等数学","content":"示例资料","source_type":"exam","tags":[],"archived":False,"revision":1}
items=[dict(id=f"q{i}",code=f"QDEMO{i:04}",kind="question",title=t,subject="高等数学",chapter="一元函数微分学",question_type="解答题",content=c,answer=a,solution=s,analysis="",proof="",unit_type="",source_type="",source_id=source["id"],tags=tags,archived=False,revision=1,sources_revision=1) for i,(t,c,a,s,tags) in enumerate([
(r"重要极限 $\lim_{x\to0}\frac{\sin x}{x}$",r"求极限 $\lim_{x\to0}\frac{\sin x}{x}$。","$1$",r"根据重要极限，$\lim_{x\to0}\frac{\sin x}{x}=1$。",["重要极限","极限运算"]),
("导数计算",r"设 $f(x)=x^2e^x$，求 $f'(x)$。",r"$e^x(x^2+2x)$","使用乘积求导法则。",["导数","乘积法则"]),
("定积分",r"计算 $\int_0^1 x^2\,dx$。",r"$\frac13$","使用牛顿—莱布尼茨公式。",["定积分"]),
("矩阵计算",r"计算 $\det\begin{pmatrix}1&2\\3&4\end{pmatrix}$。","$-2$","使用二阶行列式公式。",["行列式"])],1)]
doc={"id":"demo","title":"考研数学（一）示例试卷","kind":"intake","subject":"高等数学","source_id":source["id"],"revision":1,"archived":False,"blocks":[{"uid":q["id"],"kind":"reference","title":"","content":"","answer":"","solution":"","analysis":"","proof":"","chapter":"","question_type":"","unit_type":"","resource_id":q["id"],"file_id":None,"width":100,"snapshot":q} for q in items]}
points=[dict(id=f"p{i}",code=f"KP{i}",name=n,subject="高等数学",chapter="微积分",description="示例知识点",aliases=[],status="active",revision=1) for i,n in enumerate(["微积分","一元函数微分学","一元函数积分学","重要极限","导数","微分中值定理","定积分","换元积分法","分部积分法"])]
edges=[dict(source_id=f"p{a}",target_id=f"p{b}",relation_type="contains") for a,b in [(0,1),(0,2),(1,3),(1,4),(1,5),(2,6),(2,7),(2,8)]]
demo_chat={"id":"chat-demo","title":"录入建议示例","project":"","pinned":False,"archived":False,"updated_at":1,
 "messages":[{"id":"msg-user","role":"user","content":"请录入一道题：求 $x^2$ 的导数。","state":"done","detail":"","model":"Auto","attachments":[],"resource_refs":[]},
 {"id":"msg-ai","role":"assistant","content":"可以整理为题目草稿，请确认。\n\n### 解法说明\n\n| 方法 | 结果 |\n| --- | --- |\n| 幂函数 | $2x$ |\n\n"+'```wg-card\n{"type":"comparison","title":"解法对比","items":[{"label":"方法一","text":"直接求导"},{"label":"方法二","text":"定义法"}]}\n```',"state":"done","detail":"","model":"Auto","attachments":[],"resource_refs":[],"intake_intent":"question"}]}
review_job={"id":"review-demo","title":"补充示例","state":"review","detail":"待人工核对","revision":1,"document_id":None,"input_text":"求导数","items":[{"uid":"review-item","kind":"question","title":"导数计算","content":r"求 $x^2$ 的导数。","answer":"","solution":"","analysis":"","proof":"","chapter":"","question_type":"","unit_type":""}]}
review_clean={**review_job,"id":"review-clean","reviewed_uids":[],"items":[{**review_job["items"][0],"answer":"$2x$","solution":"幂函数求导"}]}
review_match={**review_clean,"id":"review-match","items":[{**review_clean["items"][0],"content":r"测试查重：求 $x^2$ 的导数。"}],"reviewed_uids":[]}
review_suggestion={"id":"supplement-demo","job_id":"review-demo","item_uid":"review-item","base_revision":1,"fields":["answer","solution"],"state":"review","detail":"AI生成待确认","proposal":{"answer":"$2x$","solution":r"利用幂函数求导公式，$(x^2)'=2x$。"},"accepted":[],"model":"Auto"}
ai_doc={**doc,"id":"ai-demo","blocks":[{"uid":"ai-q1","kind":"question","title":"导数计算","content":r"求 $x^2$ 的导数。","answer":"$2x$","solution":"","analysis":"","proof":"","chapter":"","question_type":"解答题","unit_type":"","resource_id":None,"file_id":None,"width":100}]}
ai_edit={"id":"edit-demo","document_id":"ai-demo","base_revision":1,"fields":["solution"],"instruction":"逐步推导","model":"Auto","state":"review","detail":"待确认","change_count":1,"changes":[{"uid":"ai-q1","field":"solution","before":"","after":r"由幂函数求导公式，$(x^2)'=2x$。"}],"accepted":[]}
registration_preview={"revision":1,"items":[{"uid":"ai-q1","candidates":[],"knowledge":[{"id":"p4","name":"导数","code":"KP4","chapter":"微积分","matched":"导数"}],"chapter_suggestion":"微积分","peer_ids":[],"missing":["solution"]}],"similar_scan_limit":300}
manual_saved={}
manual_approved={}
manual_runs={}
bank_cart={"revision":0,"ids":[]}
bank_bulk={}
layout_profiles={}
video_test_enabled=False
video_jobs=[]
video_demo={"id":"video-preview","resource_id":items[0]["id"],"resource_revision":1,"source_snapshot":{"title":items[0]["title"],"problem":items[0]["content"],"answer":items[0]["answer"],"reference_solution":items[0]["solution"],"fps":60},"engine_id":"a"*32,"work_id":None,"created_at":1}
def answer(route):
    from urllib.parse import urlsplit,parse_qs
    u=urlsplit(route.request.url);p=u.path.removeprefix("/api");q=parse_qs(u.query)
    result={
      "/auth/me":{"username":"预览管理员"},"/ready":{"status":"ok"},"/settings":{"display_name":"微光数学","theme":"light"},"/resources/subjects":subjects,
      "/knowledge/points":{"items":points,"total":len(points)},"/knowledge/relations":{"items":edges,"truncated":False},
      "/documents/demo":doc,"/documents/source-export/source-preview":{**doc,"kind":"paper","source_export":True,"has_source_content":True,"batch_count":1},"/documents/demo/origin":{"job_id":"review-demo","input_text":r"原始资料 $x^2$","provenance":{"kind":"manual"},"supplements":[]},"/resources/source-preview":source,"/documents":{"items":[{k:v for k,v in doc.items() if k!="blocks"}],"total":1},
      "/intelligence/jobs":[],"/intelligence/import/capabilities":{"text":True,"docx":True,"pdf_text":True,"image_ocr":False,"pdf_ocr":False},"/chat/sessions/chat-demo":demo_chat,"/intelligence/chat-source/msg-user":{"message_id":"msg-user","session_id":"chat-demo","role":"user","text":demo_chat["messages"][0]["content"],"title":demo_chat["title"],"has_attachments":False},"/chat/sessions":[{k:v for k,v in demo_chat.items() if k!="messages"}],"/qoder/status":{"available":True,"chat_available":True,"worker_version":4},"/qoder/models":{"source":"cli","models":[{"id":"Auto","label":"Auto","efforts":["medium","high"]}]},"/qoder/preferences":{"model":"Auto","effort":"medium","video_model":"Auto","video_effort":"medium"},
      "/settings/status":{"version":"preview","release":"synthetic-preview","disk":None},"/settings/audit":[],
      "/studio/presets":{"bilibili":[1200,900,7,7,7,7],"bilibili_wide":[1920,1080,8,8,8,8],"douyin":[1080,1440,9,12,8,8],"douyin_wide":[1440,1080,8,8,8,8],"douyin_full":[1080,1920,13,21,8,12],"xiaohongshu":[1080,1440,8,10,8,8],"wechat_channels":[1080,1260,8,10,8,8],"wechat_channels_wide":[1920,1080,8,8,8,8],"wechat_top":[900,383,6,8,28.72,28.72],"wechat_sub":[500,500,8,8,8,8]},
      "/qoder/usage/refresh":{"available":True,"source":"sdk","updated_at":1795656773,"packs":[{"kind":"userQuota","label":"套餐额度","total":100,"used":25,"remaining":75,"unit":"credits","available":True}]},"/studio/qoder-checkin":{"round":"2026-11-26","timezone":"Asia/Shanghai","accounts":[]},"/qiandao/state":{"enabled":False,"configured":False,"reason":"pat_missing","round":"2026-11-26","next_round":"2026-11-27T10:00:00+08:00","current":None,"history":[]},"/studio":{"items":[],"total":0},"/video/status":{"available":False,"detail":"隔离预览：未配置视频引擎","source_revision":"preview"},"/video/projects":[],"/tasks":[],"/files/stats":{"count":0,"bytes":0,"max_file_bytes":20971520}
    }.get(p)
    if p=="/intelligence/jobs/review-agent-match":result={**review_job,"id":"review-agent-match","reviewed_uids":[]}
    if p=="/intelligence/jobs/review-agent-match/supplements":result=[]
    if p=="/workspaces/agent-work-demo/agent/matching":
        if route.request.method=="POST":
            payload=route.request.post_data_json
            assert payload=={"plan_id":"agent-plan","job_id":"review-agent-match","revision":1,"source_batch_id":"reference-batch"}
            result={**review_suggestion,"state":"failed","detail":"测试：无可靠原文","proposal":{}}
        elif q.get("job_id")==["review-agent-match"]:
            result={"plan_id":"agent-plan","job_id":"review-agent-match","revision":1,"fields":["answer"],"pending":False,"candidates":[{"batch_id":"reference-batch","file_id":"reference-file","file_name":"参考答案.pdf","start":21,"end":25,"eligible_count":1,"targets":[{"uid":"review-item","title":"导数计算","fields":["answer"]}]}],"unavailable":[]}
        else:
            route.fulfill(status=200,content_type="application/json",body="null");return
    if p=="/intake-records":
        records=[{"id":"d:demo","title":doc["title"],"source_type":"exam","method":"manual","status":"registered","href":"/intake?doc=demo","action":"查看资料","actions":[{"state":"registered","label":"查看资料","href":"/intake?doc=demo"}],"progress":["4 道题"],"file_names":[],"updated_at":1,"hidden":False},{"id":"j:review-demo","title":"AI 审核示例","source_type":"uncategorized","method":"ai","status":"review","href":"/work?job=review-demo&review=1","action":"继续审核","actions":[{"state":"review","label":"继续审核","href":"/work?job=review-demo&review=1"}],"progress":["0/1 条已审核"],"file_names":[],"updated_at":2,"hidden":False}]
        records=[r for r in records if (not q.get("q") or q["q"][0] in r["title"]) and (not q.get("status") or q["status"][0]==r["status"]) and (not q.get("source_type") or q["source_type"][0]==r["source_type"]) and (not q.get("method") or q["method"][0]==r["method"])]
        result={"items":records,"total":len(records)}
    if p=="/workspaces":result=[]
    if p=="/workspaces/agent-work-demo":
        result={"id":"agent-work-demo","title":"持续工作预览","materials":[{"id":"agent-material","file":{"id":"agent-pdf","name":"高等数学.pdf","media_type":"application/pdf"},"total_units":100,"verified_units":5,"next_unit":6,"batches":[{"id":"agent-batch","start":1,"end":5,"units":[],"verified":True}]}]}
    if p=="/workspaces/agent-work-demo/agent/history":
        result=[{"id":"old-agent-plan","instruction":"先识别旧教材","model":"Auto","effort":"default","state":"cancelled","detail":"已取消","plan":{"action":"recognize","file_name":"旧教材.pdf","explanation":"历史计划"}}]
    if p in ("/workspaces/agent-work-demo/agent","/workspaces/agent-work-demo/agent/advance"):
        advancing=p.endswith("/advance")
        if advancing:assert route.request.method=="POST" and route.request.post_data_json["plan_id"]=="agent-plan"
        result={"id":"agent-plan","instruction":"核对五页后继续整理","model":"Auto","effort":"medium","state":"dispatched","detail":"已进入工作流程","plan":{"action":"recognize","file_id":"agent-pdf","file_name":"高等数学.pdf","start":1,"end":5,"unit":"页","goal":"review","focus":"question","explanation":"识别后核对，再整理"},"result":{"material_id":"agent-material","action":"recognize","batch_id":"agent-batch"},"workflow":{"stage":"organizing" if advancing else "organize","detail":"等待AI整理结果" if advancing else "原文已核对，可以按计划继续AI整理","material_id":"agent-material","batch_id":"agent-batch","job_id":"review-demo" if advancing else None,"goal":"review","recognized":5,"total":5,"verified":True,"references":[]}}
    if video_test_enabled:
        if p=="/video/status":result={"available":True,"detail":"隔离测试引擎","source_revision":"preview"}
        if p=="/video/projects":result=video_demo if route.request.method=="POST" else [video_demo]
        if p=="/video/projects/video-preview":result={**video_demo,"lesson":{"status":"ready","has_video":False,"video_review_status":"pending","revision":1},"jobs":video_jobs.copy()}
        if p=="/video/projects/video-preview/generate" and route.request.method=="POST":
            video_jobs[:]=[{"id":"b"*32,"kind":"generate","status":"running","phase":"正在生成代码","overall":37}]
            result={"id":"b"*32}
    if p.startswith("/resources/") and p.count("/")==2:
        match=next((r for r in items if p=="/resources/"+r["id"]),None)
        if match is not None:result=match
    if p=="/documents" and route.request.method=="POST":
        body=json.loads(route.request.post_data)
        result={**body,"id":"assembly-demo","archived":False,"revision":1,"blocks":[{**b,"snapshot":next(r for r in items if r["id"]==b["resource_id"])} if b["kind"]=="reference" else b for b in body["blocks"]]}
    if p=="/documents/assembly-demo" and route.request.method=="PUT":
        body=json.loads(route.request.post_data)
        result={**body,"revision":body["revision"]+1}
    if p=="/documents/ai-demo":
        result=ai_doc
        if route.request.method=="PUT":
            result={**json.loads(route.request.post_data),"revision":2}
    if p=="/documents/setup" and route.request.method=="POST":
        body=json.loads(route.request.post_data)
        result={**doc,"id":"setup-demo","title":body["title"],"subject":"","blocks":[]}
    if p.endswith("/manual-draft") and route.request.method=="PUT":
        body=json.loads(route.request.post_data)
        result={**body,"revision":body["revision"]+1}
        manual_saved[body["id"]]=result
    if p.endswith("/manual-review") and route.request.method=="POST":
        body=manual_saved.get(p.split("/")[2],ai_doc)
        rows=[{"uid":b["uid"],"number":i+1,"kind":b["kind"],"title":b.get("title") or b["content"][:80],"action":"create","errors":[],"warnings":["答案未填写"] if not b.get("answer") else []} for i,b in enumerate(body["blocks"]) if b["kind"] in ("question","knowledge")]
        result={"revision":body["revision"],"rows":rows,"reviewed_uids":manual_approved.get(p.split("/")[2],[])}
    if p.endswith("/manual-review-progress") and route.request.method=="POST":
        ident=p.split("/")[2]
        body=json.loads(route.request.post_data)
        approved=manual_approved.setdefault(ident,[])
        if body["approved"] and body["uid"] not in approved:approved.append(body["uid"])
        elif not body["approved"] and body["uid"] in approved:approved.remove(body["uid"])
        result={"revision":body["revision"],"reviewed_uids":approved}
    if p.endswith("/intake-preview") and route.request.method=="POST":
        ident=p.split("/")[2];body=manual_saved.get(ident,ai_doc)
        rows=[{"uid":b["uid"],"number":i+1,"kind":b["kind"],"title":b.get("title") or b["content"][:80],"action":"create","errors":[],"warnings":["答案未填写"] if not b.get("answer") else [],"approved":b["uid"] in manual_approved.get(ident,[]),"original_question_number":""} for i,b in enumerate(body["blocks"]) if b["kind"] in ("question","knowledge")]
        result={"preview_token":"a"*64,"revision":body["revision"],"source":{"id":body.get("source_id") or "src","title":body["title"],"revision":1},"rows":rows,"total":len(rows),"batch_size":20,"batches":1}
    if p.endswith("/intake-run"):
        ident=p.split("/")[2]
        if route.request.method=="GET":result=manual_runs.get(ident)
        else:
            body=manual_saved.get(ident,ai_doc)
            uids=[b["uid"] for b in body["blocks"] if b["kind"] in ("question","knowledge")]
            counts={"question_create":0,"question_reuse":0,"knowledge_create":0,"knowledge_reuse":0,"updated":0,"methods_added":0,"source_occurrences":0,"evaluation_queued":0}
            result={"id":"test-run-"+ident,"document_id":ident,"base_revision":body["revision"],"revision":body["revision"],"source":{"id":body.get("source_id") or "src","title":body["title"],"revision":1},"state":"ready","total":len(uids),"completed":0,"next_batch":0,"batches":[{"index":0,"uids":uids,"state":"pending"}],"counts":counts,"error":""}
            manual_runs[ident]=result
    if p.endswith("/intake-run/step") and route.request.method=="POST":
        ident=p.split("/")[2];body=manual_saved.get(ident,ai_doc);run=manual_runs[ident]
        saved=[{**b,"kind":"reference","resource_id":"saved-"+b["uid"],"snapshot":{**b,"id":"saved-"+b["uid"],"code":"QNEW","revision":1}} if b["kind"] in ("question","knowledge") else b for b in body["blocks"]]
        counts={**run["counts"],"question_create":sum(b["kind"]=="question" for b in body["blocks"]),"knowledge_create":sum(b["kind"]=="knowledge" for b in body["blocks"]),"source_occurrences":run["total"]}
        run={**run,"state":"completed","completed":run["total"],"revision":body["revision"]+1,"next_batch":1,"counts":counts,"batches":[{**run["batches"][0],"state":"completed","record_id":"test-receipt"}]}
        manual_runs[ident]=run
        manual_saved[ident]={**body,"blocks":saved,"revision":body["revision"]+1}
        result={"document":manual_saved[ident],"run":run}
    if p.endswith("/manual-commit") and route.request.method=="POST":
        body=manual_saved[p.split("/")[2]]
        saved=[{**b,"kind":"reference","resource_id":"saved-"+b["uid"],"snapshot":{**b,"id":"saved-"+b["uid"],"code":"QNEW","revision":1}} if b["kind"] in ("question","knowledge") else b for b in body["blocks"]]
        result={"document":{**body,"blocks":saved,"revision":body["revision"]+1},"counts":{"question_create":sum(b["kind"]=="question" for b in body["blocks"]),"knowledge_create":sum(b["kind"]=="knowledge" for b in body["blocks"]),"question_reuse":0,"knowledge_reuse":0,"updated":0}}
    if p=="/documents/manual-matches" and route.request.method=="POST":
        body=json.loads(route.request.post_data)
        matches=[{"resource":items[1],"match_kind":"similar","similarity":.87},{"resource":items[2],"match_kind":"similar","similarity":.80}] if "测试查重" in body["content"] else []
        result={"items":matches,"scanned":len(items),"threshold":.80,"total":len(matches),"scope":"full_active_question_bank"}

    if p in ("/documents/ai-demo/manual-save","/documents/demo/manual-save") and route.request.method=="POST":
        body=json.loads(route.request.post_data)
        saved=[]
        for b in body["blocks"]:
            if b.get("edit_reference_revision"):
                snapshot={**b["snapshot"],**{key:b[key] for key in ("title","content","answer","solution","analysis","proof","question_type")},"revision":b["edit_reference_revision"]+1}
                saved.append({**b,"edit_reference_revision":None,"snapshot":snapshot})
            elif b["kind"] in ("question","knowledge"):
                saved.append({**b,"kind":"reference","resource_id":"saved-"+b["uid"],"snapshot":{**b,"code":"QNEW","kind":b["kind"],"id":"saved-"+b["uid"],"revision":1}})
            else:saved.append(b)
        result={**body,"revision":body["revision"]+1,"blocks":saved}
    if p=="/documents/ai-demo/ai-edits":result=[ai_edit]
    if p.endswith("/registration-history"):result=[]
    if p=="/documents/ai-demo/registration-preview":result=registration_preview
    if p=="/documents/ai-demo/ai-edits/edit-demo":result=ai_edit
    if p=="/intelligence/jobs/review-demo":result=review_job
    if p=="/intelligence/jobs/review-demo/supplements":result=[review_suggestion]
    if p in ("/intelligence/jobs/review-clean","/intelligence/jobs/review-match"):
        row=review_clean if p.endswith("review-clean") else review_match
        if route.request.method=="PUT":
            data=route.request.post_data_json
            assert data["revision"]==row["revision"]
            if any(x["uid"] in data["reviewed_uids"] and "测试查重" in x["content"] and not (x.get("dedup_reason") or x.get("reuse_resource_id")) for x in data["items"]):
                route.fulfill(status=409,content_type="application/json",body=json.dumps({"detail":"存在重复候选，请查看查重结果"}))
                return
            row.update(items=data["items"],reviewed_uids=data["reviewed_uids"],revision=row["revision"]+1)
        result=row
    if p in ("/intelligence/jobs/review-clean/supplements","/intelligence/jobs/review-match/supplements"):result=[]
    if p=="/files" and route.request.method=="POST":
        name=q.get("name",["demo.tex"])[0]
        result={"id":"12345678-1234-4321-8765-123456789abc","name":name,"media_type":"image/png","previewable":True} if name.endswith(".png") else {"id":"file-demo","name":name,"media_type":"text/plain","previewable":False}
    if p=="/files/12345678-1234-4321-8765-123456789abc/preview":
        import base64
        route.fulfill(status=200,content_type="image/png",body=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/b1sAAAAASUVORK5CYII="))
        return
    if p=="/intelligence/import" and route.request.method=="POST":
        result={"import_id":"import-demo","file_id":"file-demo","file_name":"demo.tex","text":r"求 $\frac{1}{x}$ 的导数。","method":"text","start":1,"end":1,"total_units":None,"warnings":[]}
    if p=="/bank/cart":
        if route.request.method=="PUT":
            v=route.request.post_data_json
            assert v["revision"]==bank_cart["revision"]
            bank_cart.update(revision=bank_cart["revision"]+1,ids=v["ids"])
        result={**bank_cart,"items":[r for ident in bank_cart["ids"] for r in items if r["id"]==ident]}
    if p=="/bank/bulk":result=list(bank_bulk.values())
    if p=="/bank/bulk/preview":
        v=route.request.post_data_json
        plan={"id":"bulk-demo","state":"preview","next":0,"rows":[{**r,"code":next(x["code"] for x in items if x["id"]==r["id"]),"state":"ready","reason":""} for r in v["items"]]}
        bank_bulk[plan["id"]]=plan;result=plan
    if p=="/bank/bulk/bulk-demo":result=bank_bulk["bulk-demo"]
    if p=="/bank/bulk/bulk-demo/step":
        plan=bank_bulk["bulk-demo"];plan.update(state="completed",next=len(plan["rows"]));plan["rows"]=[{**r,"state":"done"} for r in plan["rows"]];result=plan
    if p=="/resources":
        rows=[source] if q.get("kind")==["source"] else items
        if q.get("bank_summary")==["true"]:rows=[{**r,"bank_summary":{"source_count":2 if i==0 else 1,"source_title":source["title"],"method_count":2 if i==0 else 1,"has_answer":bool(r.get("answer")),"has_solution":bool(r.get("solution"))}} for i,r in enumerate(rows)]
        result={"items":[{"id":r["id"],"revision":r["revision"]} for r in rows] if q.get("selection_only")==["true"] else rows,"total":len(rows)}
    if p=="/knowledge/browse":
        pool=[p for p in points if p["subject"]==q.get("subject",[""])[0]]
        ids={p["id"] for p in pool}
        relations=[e for e in edges if e["source_id"] in ids and e["target_id"] in ids and e["relation_type"]=="contains"]
        roots=[p for p in pool if p["id"] not in {e["target_id"] for e in relations}]
        term=q.get("q",[""])[0]
        parent=q.get("parent_id",[""])[0]
        if term:
            rows=[p for p in pool if term in p["name"]]
        elif parent:
            rows=[p for p in pool if p["id"] in {e["target_id"] for e in relations if e["source_id"]==parent}]
        elif "chapter" in q:
            rows=[p for p in roots if p["chapter"]==q["chapter"][0]]
        else:
            rows=None
        if rows is None:
            chapters=sorted({p["chapter"] for p in roots})
            result={"mode":"chapters","items":[{"chapter":c,"count":sum(p["chapter"]==c for p in roots)} for c in chapters],"total":len(chapters)}
        else:
            result={"mode":"points","items":[{**p,"child_count":sum(e["source_id"]==p["id"] for e in relations)} for p in rows],"total":len(rows)}
    if p.startswith("/settings/document-layout/") or p=="/settings/document-templates":
        record=layout_profiles.get(p,{"revision":0,"value":[] if p.endswith("document-templates") else None,"history":[]})
        if route.request.method=="PUT":
            body=route.request.post_data_json
            if body["revision"]!=record["revision"]:
                route.fulfill(status=409,content_type="application/json",body=json.dumps({"detail":"配置版本冲突"}));return
            record={"revision":record["revision"]+1,"value":body["value"],"history":([{"revision":record["revision"],"value":record["value"]}]+record["history"])[:2] if record["revision"] else []}
            layout_profiles[p]=record
        result=record
    if p.startswith("/knowledge/points/") and p.endswith("/resources"):result=[]
    if result is None:result={}
    route.fulfill(status=200,content_type="application/json",body=json.dumps(result,ensure_ascii=False))

GROUP=os.environ.get("WG_UI_GROUP","all")
if GROUP not in {"all","desktop","editors","mobile"}:
    raise ValueError("Unknown UI test group: "+GROUP)
SCREENSHOTS=os.environ.get("WG_UI_SCREENSHOTS","1")=="1"
EDITOR_PAGES={"04-word","25-word-ai","06-cover"}

def capture(page, *, path, full_page=False):
    if SCREENSHOTS:
        page.evaluate("document.fonts.ready")
        page.screenshot(path=path,full_page=full_page)

def visit(page, path, ready=None):
    # A concrete UI readiness check replaces generic network idle when available.
    page.goto("http://127.0.0.1:4173"+path,
              wait_until="domcontentloaded" if ready else "networkidle")
    if ready:
        page.locator(ready).first.wait_for()

READY={
    "00-home":".chat-home-recent",
    "29-overview":".chat-home-recent",
    "12-create":".project-hub .project-link",
    "13-video":".video-new-card",
    "01-intake":".intake-entry",
    "16-intake-document":".legacy-intake",
    "05-chat":".chat-home-recent",
    "19-intake-intent":".chat-intake-suggestion",
    "22-intake-supplement":".wg-work-result",
    "25-word-ai":".manual-word-work",
    "04-word":".manual-word-work .katex",
    "06-cover":".fc-art",
}

with sync_playwright() as p:
    # Hosted CI already supplies Chrome; local developers can use Playwright Chromium.
    channel=os.environ.get('WG_BROWSER_CHANNEL')
    browser=p.chromium.launch(headless=True, **({'channel':channel} if channel else {}))
    context=browser.new_context(viewport={"width":1600,"height":900},device_scale_factor=1)
    context.route("**/api/**",answer)
    page=context.new_page()
    try:
        if GROUP in {'all','desktop'}:
            print('UI case: app shell responsive geometry and drawer state',flush=True)
            visit(page,"/",".chat-home-recent")
            for width,sidebar_width in ((1600,210),(1024,210),(900,186),(761,186)):
                page.set_viewport_size({"width":width,"height":900})
                page.wait_for_function("(w)=>Math.abs(document.querySelector('.shell > .nav').getBoundingClientRect().width-w)<1",arg=sidebar_width)
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.get_by_role("button",name="收起侧边栏",exact=True).click()
            page.wait_for_function("Math.abs(document.querySelector('.shell > .nav').getBoundingClientRect().width-58)<1")
            for width in (760,430,390,360):
                page.set_viewport_size({"width":width,"height":873})
                page.wait_for_function("!document.querySelector('.shell').classList.contains('is-collapsed')")
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.get_by_role("button",name="打开导航",exact=True).click()
            page.wait_for_function("document.querySelector('.shell > .nav').classList.contains('open')")
            page.wait_for_function("Math.abs(document.querySelector('.shell > .nav').getBoundingClientRect().width-300)<1")
            page.set_viewport_size({"width":1600,"height":900})
            page.wait_for_function("document.querySelector('.shell').classList.contains('is-collapsed') && !document.querySelector('.shell > .nav').classList.contains('open')")
            page.get_by_role("button",name="展开侧边栏",exact=True).click()
            page.wait_for_function("Math.abs(document.querySelector('.shell > .nav').getBoundingClientRect().width-210)<1")
        if GROUP in {'all','desktop'}:
            print('UI case: combined work and chat history',flush=True)
            def nav_job_fixture(route):
                route.fulfill(json=[{"id":"review-demo","title":"导航工作记录测试","state":"review","updated_at":2}])
            page.route("**/api/intelligence/jobs",nav_job_fixture)
            visit(page,"/",".chat-home-recent")
            nav=page.locator("#workspace-navigation")
            expect(nav.get_by_role("link",name="导航工作记录测试",exact=True)).to_be_visible()
            nav.locator(".nav-combined-history").get_by_role("button",name="全部",exact=True).click()
            nav.get_by_label("记录类型").select_option("work")
            expect(nav.get_by_role("link",name="导航工作记录测试",exact=True)).to_be_visible()
            expect(nav.get_by_text(demo_chat["title"],exact=True)).to_have_count(0)
            nav.get_by_label("搜索会话").fill("不存在的记录")
            expect(nav.get_by_role("link",name="导航工作记录测试",exact=True)).to_have_count(0)
            nav.get_by_label("搜索会话").fill("")
            nav.get_by_role("link",name="导航工作记录测试",exact=True).click()
            page.wait_for_url("**/work?job=review-demo")
            nav.locator(".nav-combined-history").get_by_role("button",name="收起",exact=True).click()
            page.unroute("**/api/intelligence/jobs",nav_job_fixture)
            visit(page,"/",".chat-home-recent")
        if GROUP in {'all','desktop'}:
            print('UI case: actual branch request and session read retry',flush=True)
            branch_requests=[]
            def branch_turn(route):
                payload=json.loads(route.request.post_data)
                branch_requests.append(payload)
                route.fulfill(json={**demo_chat,"id":"chat-branch-demo","title":"分支测试"})
            def branch_read(route):
                route.fulfill(json={**demo_chat,"id":"chat-branch-demo","title":"分支测试"})
            page.route("**/api/chat/sessions/chat-demo/turn",branch_turn)
            page.route("**/api/chat/sessions/chat-branch-demo",branch_read)
            visit(page,"/chat?session=chat-demo",".chat-intake-suggestion")
            retry=page.get_by_role("button",name="重新生成回答",exact=True)
            expect(retry).to_be_enabled()
            retry.click()
            page.get_by_role("dialog",name="重新生成回答").get_by_role("button",name="创建分支",exact=True).click()
            page.wait_for_url("**/chat?session=chat-branch-demo")
            assert len(branch_requests)==1
            assert branch_requests[0]["rewind_id"]=="msg-user"
            assert branch_requests[0]["content"]==demo_chat["messages"][0]["content"]
            page.unroute("**/api/chat/sessions/chat-demo/turn",branch_turn)
            page.unroute("**/api/chat/sessions/chat-branch-demo",branch_read)
            failures=[]
            recovered=[False]
            def read_retry(route):
                failures.append(1)
                if not recovered[0]:
                    route.fulfill(status=503,json={"detail":"测试会话暂不可用"})
                else:
                    route.fulfill(json=demo_chat)
            page.route("**/api/chat/sessions/chat-demo",read_retry)
            visit(page,"/chat?session=chat-demo",".workspace-feedback.error")
            expect(page.get_by_role("button",name="发送消息")).to_be_disabled()
            recovered[0]=True
            page.get_by_role("button",name="重新加载",exact=True).click()
            expect(page.locator(".chat-intake-suggestion")).to_be_visible()
            assert len(failures)>=2
            page.unroute("**/api/chat/sessions/chat-demo",read_retry)
            visit(page,"/",".chat-home-recent")
        if GROUP in {'all','desktop','editors'}:
            for path,name in [("/","00-home"),("/overview","29-overview"),("/library","11-library"),("/create","12-create"),("/videos","13-video"),("/products","14-products"),("/operations","15-operations"),("/intake","01-intake"),("/intake?mode=document","16-intake-document"),("/intake-single?kind=knowledge","17-intake-knowledge"),("/intelligence","18-intelligence"),("/intelligence?job=review-demo","22-intake-supplement"),("/resources","02-bank"),("/graph","03-graph"),("/intake?doc=demo","04-word"),("/intake?doc=ai-demo","25-word-ai"),("/chat","05-chat"),("/chat?session=chat-demo","19-intake-intent"),("/covers","06-cover"),("/checkin","07-checkin"),("/settings","08-settings")]:
                if GROUP!="all" and ((name in EDITOR_PAGES) != (GROUP=="editors")):
                    continue
                print("UI case:",name,flush=True)
                visit(page,path,READY.get(name))
                page.wait_for_selector(".legacy-shell",timeout=10000)
                # Preserve the original alternative, without passing a bool to expect().
                if not page.locator(".main-section-links").is_visible():
                    expect(page.locator(".nav")).to_have_count(1)
                assert page.locator(".mobile-tabs,.clean-context-menu,.clean-local-nav").count()==0
                page.evaluate("document.fonts.ready")
                if name=="01-intake":
                    expect(page.locator(".intake-entry")).to_have_count(2)
                    expect(page.locator(".intake-entry[href='/work?workspace=new']")).to_be_visible()
                    expect(page.locator(".intake-entry[href='/intake?mode=document']")).to_be_visible()
                    assert page.locator(".intake-hub a[href^='/intake-single']").count()==0
                    expect(page.get_by_label("资料类型",exact=True)).to_be_visible()
                    expect(page.locator(".intake-record")).to_have_count(2)
                    page.get_by_role("button",name="待审核",exact=True).click()
                    expect(page.locator(".intake-record")).to_have_count(1)
                    expect(page.locator(".intake-record-name")).to_contain_text("AI 审核示例")
                    page.locator(".intake-state-tabs").get_by_role("button",name="全部",exact=True).click()
                    expect(page.locator(".intake-record")).to_have_count(2)
                    page.get_by_label("搜索资料",exact=True).fill("考研")
                    expect(page.locator(".intake-record")).to_have_count(1)
                    expect(page.locator(".intake-record-name")).to_contain_text("考研")
                    page.get_by_label("搜索资料",exact=True).fill("")
                    expect(page.get_by_label("搜索资料",exact=True)).to_have_value("")
                    expect(page.locator(".intake-record")).to_have_count(2)
                if name=="16-intake-document":
                    expect(page.get_by_text("整份资料不限定科目，逐条填写科目。",exact=True)).to_be_visible()
                    page.get_by_role("button",name="试卷",exact=True).click()
                    expect(page.get_by_label("考试年份")).to_be_visible()
                    page.get_by_role("button",name="其他",exact=True).click()
                    expect(page.get_by_label("资料来源")).to_be_visible()
                    assert page.get_by_label("默认科目",exact=True).count()==0
                    page.get_by_role("button",name="复用已有来源").click()
                    page.get_by_label("选择来源资料",exact=True).first.click()
                    page.locator(".math-choice-options").get_by_role("button").filter(has_text="SDEMO0001").click()
                    expect(page.locator(".source-selected")).to_be_visible()
                    assert page.get_by_label("录入批次名称").input_value()==source["title"]
                    capture(page,path=str(OUT/"21-source-reuse.png"),full_page=False)
                if name=="17-intake-knowledge":
                    assert page.get_by_role("button",name="知识单元",exact=True).get_attribute("aria-pressed")=="true"
                if name=="05-chat":
                    assert page.locator("#mode-more-panel .reasoning-effort").count()==0
                    page.get_by_role("button",name="打开模型选择",exact=True).click()
                    effort=page.locator(".composer-inference-panel").get_by_role("button",name="高",exact=True)
                    effort.wait_for()
                    effort.click()
                    expect(page.locator(".composer-inference-panel")).to_have_count(0)
                    page.get_by_role("button",name="打开模型选择",exact=True).click()
                    expect(page.locator(".composer-inference-panel").get_by_role("button",name="高",exact=True)).to_have_attribute("aria-pressed","true")
                    page.keyboard.press("Escape")
                    expect(page.locator(".composer-inference-panel")).to_have_count(0)
                    assert page.locator(".intake-chat-prompts").count()==0
                    expect(page.locator(".chat-home-recent")).to_be_visible()
                    expect(page.get_by_role("heading",name="今天想研究什么？")).to_be_visible()
                    expect(page.locator("[data-chat-layout=v3] .ai-home-shortcuts > button")).to_have_count(2)
                    expect(page.get_by_role("button",name="检索题库",exact=True)).to_be_visible()
                    page.get_by_role("button",name="检索题库",exact=True).click()
                    expect(page.get_by_label("检索题库编号、标题或正文")).to_be_visible()
                    page.locator(".chat-reference-picker").get_by_role("button",name="关闭").click()
                    assert page.get_by_role("button",name="发送消息").locator("svg").count()==1
                    page.get_by_label("输入消息").fill(r"录入题目：求 $\lim_{x\to0}\frac{\sin x}{x}$。")
                    page.get_by_role("button",name="添加与工具").click()
                    page.get_by_role("button",name="转录入",exact=True).click()
                    page.wait_for_url("**/work")
                    assert page.get_by_label("输入录入资料",exact=True).input_value().startswith("录入题目")
                    expect(page.get_by_text("已带入聊天正文")).to_be_visible()
                    visit(page,"/chat",".chat-home-recent")
                if name=="22-intake-supplement":
                    expect(page.get_by_role("link",name="进入审核工作台",exact=True)).to_be_visible()
                    page.get_by_role("link",name="进入审核工作台",exact=True).click()
                    page.locator(".supplement-proposal .katex").first.wait_for()
                    expect(page.locator(".wg-review-editor .katex").first).to_be_visible()
                    assert page.get_by_role("button",name="确认生成录入文档").is_disabled()
                    assert page.get_by_role("button",name="确认选中补充内容").is_enabled()
                    expect(page.locator(".supplement-proposal").get_by_text("待审核 · AI生成内容")).to_be_visible()
                if name=="18-intelligence":
                    assert page.locator("#mode-more-panel .reasoning-effort").count()==0
                    page.get_by_role("button",name="打开模型选择",exact=True).click()
                    effort=page.locator(".composer-inference-panel").get_by_role("button",name="高",exact=True)
                    effort.wait_for()
                    effort.click()
                    expect(page.locator(".composer-inference-panel")).to_have_count(0)
                    page.get_by_role("button",name="打开模型选择",exact=True).click()
                    expect(page.locator(".composer-inference-panel").get_by_role("button",name="高",exact=True)).to_have_attribute("aria-pressed","true")
                    page.keyboard.press("Escape")
                    expect(page.locator(".composer-inference-panel")).to_have_count(0)
                    page.get_by_label("选择录入文件").set_input_files({"name":"demo.tex","mimeType":"text/plain","buffer":b"test formula"})
                    page.get_by_role("button",name="发送资料").click()
                    page.locator(".work-review-preview .katex").first.wait_for()
                    assert page.get_by_label("输入录入资料",exact=True).input_value()==r"求 $\frac{1}{x}$ 的导数。"
                    assert page.locator(".intelligence-stages").count()==0
                    assert page.locator(".material-import").count()==0
                if name=="19-intake-intent":
                    page.locator(".chat-intake-suggestion").wait_for()
                    expect(page.locator(".rich-reply table")).to_be_visible()
                    trace=page.locator(".wg-execution-toggle").first
                    expect(trace).to_be_visible()
                    trace.click()
                    expect(page.locator(".wg-execution-detail")).to_be_visible()
                    expect(page.locator(".rich-card").get_by_role("button",name="方法二")).to_be_visible()
                    page.locator(".rich-card").get_by_role("button",name="方法二").click()
                    expect(page.locator(".rich-card").get_by_text("定义法",exact=True)).to_be_visible()
                    assert page.locator(".chat-message.user .chat-message-body").evaluate("(el)=>getComputedStyle(el).width !== getComputedStyle(el.parentElement).width")
                    expect(page.locator(".chat-message-actions").get_by_role("button",name="复制",exact=True).first).to_be_visible()
                    expect(page.get_by_role("button",name="重新生成回答",exact=True)).to_be_visible()
                    page.locator(".chat-message.assistant").first.hover()
                    page.get_by_role("button",name="重新生成回答",exact=True).click()
                    dialog=page.get_by_role("dialog",name="重新生成回答")
                    expect(dialog).to_contain_text("保留原对话")
                    dialog.get_by_role("button",name="取消",exact=True).click()
                    expect(page.locator(".chat-message.user")).to_have_count(1)
                    assert page.locator(".clean-chat header,.clean-chat .chat-top").count()==0
                    page.get_by_role("button",name="更多选项",exact=True).click()
                    page.locator("#chat-session-actions").get_by_role("button",name="管理",exact=True).wait_for()
                    page.get_by_role("button",name="更多选项",exact=True).click()
                    capture(page,path=str(OUT/(name+".png")),full_page=False)
                    page.get_by_role("button",name="使用本次用户原文").click()
                    page.wait_for_url("**/work?from=msg-user&intent=question")
                    page.get_by_label("输入录入资料",exact=True).wait_for()
                    page.get_by_text("已带入聊天正文").wait_for()
                    assert page.get_by_label("输入录入资料",exact=True).input_value()==demo_chat["messages"][0]["content"]
                    page.get_by_role("button",name="添加录入资料").click()
                    assert page.get_by_label("录入目标").input_value()=="question"
                    page.get_by_role("button",name="添加录入资料").click()
                    capture(page,path=str(OUT/"20-intake-linked.png"),full_page=False)
                    continue
                if name=="00-home":
                    expect(page.get_by_role("link",name="任务中心",exact=True)).to_have_count(0)
                    expect(page.get_by_label("输入消息")).to_be_visible()
                    expect(page.locator(".clean-chat.chat-main-area")).to_have_count(1)
                    assert page.locator(".clean-chat .chat-main-area").count()==0
                    expect(page.locator(".workspace > header")).to_have_count(1)
                    assert page.locator(".clean-chat header,.clean-chat .chat-top").count()==0
                    expect(page.locator(".clean-chat > .chat-composer > textarea")).to_have_count(1)
                    assert page.get_by_label("输入消息").evaluate("(el) => getComputedStyle(el).borderTopWidth === '0px' && getComputedStyle(el).boxShadow === 'none'")
                    assert page.get_by_text("今天想做什么？",exact=True).count()==0
                    expect(page.locator(".chat-home-recent")).to_be_visible()
                    assert page.locator(".ai-home").evaluate("""el=>{const a=el.getBoundingClientRect(),h=el.querySelector(".ai-home-welcome").getBoundingClientRect(),f=el.querySelector(".compact-composer").getBoundingClientRect(),s=el.querySelector(".ai-home-shortcuts").getBoundingClientRect();return h.bottom<=f.top&&f.bottom<=s.top&&Math.abs((h.top+s.bottom)/2-(a.top+a.bottom)/2)<60}""")
                    assert page.locator(".mode-switch").get_by_role("link",name="聊天").get_attribute("aria-current")=="page"
                    # Only an explicit mode switch preserves unsent drafts without discarding.
                    page.get_by_label("输入消息").fill("尚未发送的教研草稿")
                    page.locator(".mode-switch").get_by_role("link",name="工作").click()
                    expect(page.get_by_label("输入录入资料")).to_be_visible()
                    page.get_by_label("输入录入资料").fill("待提交的录入正文")
                    page.locator(".mode-switch").get_by_role("link",name="聊天").click()
                    expect(page.get_by_label("输入消息")).to_have_value("尚未发送的教研草稿")
                    # Ordinary business navigation still protects dirty input.
                    page.locator("#workspace-navigation").get_by_role("link",name="教学教研",exact=True).click()
                    dialog=page.get_by_role("dialog",name="离开当前页面")
                    expect(dialog).to_be_visible()
                    dialog.get_by_role("button",name="取消",exact=True).click()
                    expect(page.get_by_label("输入消息")).to_have_value("尚未发送的教研草稿")
                    page.get_by_label("输入消息").fill("")
                    page.get_by_role("button",name="更多选项",exact=True).click()
                    assert page.locator("#mode-more-panel").get_by_role("link",name="AI 登录与模型").get_attribute("href")=="/qoder"
                    page.get_by_role("button",name="更多选项",exact=True).click()
                    page.locator(".mode-switch").get_by_role("link",name="工作").click()
                    expect(page.get_by_label("输入录入资料")).to_have_value("待提交的录入正文")
                    page.get_by_label("输入录入资料").fill("")
                    expect(page.get_by_role("button",name="添加录入资料")).to_be_visible()
                    page.get_by_role("button",name="添加录入资料").click()
                    page.get_by_role("button",name="上传图片、PDF 或 Word").wait_for()
                    page.get_by_role("button",name="添加录入资料").click()
                    page.get_by_label("选择录入文件").set_input_files({"name":"demo.tex","mimeType":"text/plain","buffer":b"test formula"})
                    page.locator(".mode-switch").get_by_role("link",name="聊天").click()
                    page.locator(".mode-switch").get_by_role("link",name="工作").click()
                    expect(page.get_by_role("button",name="移除资料")).to_be_visible()
                    expect(page.locator(".work-file")).to_contain_text("demo.tex")
                    page.get_by_role("button",name="发送资料").click()
                    page.locator(".work-review-preview .katex").first.wait_for()
                    page.get_by_role("button",name="移除资料").click()
                    page.get_by_role("dialog",name="确认操作").get_by_role("button",name="确认",exact=True).click()
                    expect(page.get_by_role("button",name="移除资料")).to_have_count(0)
                    assert page.locator(".mode-switch").get_by_role("link",name="工作").get_attribute("aria-current")=="page"
                    page.get_by_role("button",name="更多选项",exact=True).click()
                    expect(page.locator("#mode-more-panel").get_by_role("link",name="AI 登录与模型")).to_be_visible()
                    expect(page.locator("#mode-more-panel").get_by_role("link",name="任务中心",exact=True)).to_have_count(0)
                    page.get_by_role("button",name="更多选项",exact=True).click()
                    assert page.locator(".workflow-board").count()==0
                    page.locator(".mode-switch").get_by_role("link",name="聊天").click()
                    page.locator(".chat-home-recent").wait_for()
                    assert page.locator(".chat-history").count()==0
                    assert page.locator(".workflow-step").count()==0
                    expect(page.locator(".clean-recent").get_by_text(demo_chat["title"],exact=True)).to_be_visible()
                    page.locator(".clean-recent").get_by_text(demo_chat["title"],exact=True).click()
                    page.locator(".chat-intake-suggestion").wait_for()
                    page.locator("#workspace-navigation").get_by_role("link",name="新建对话").click()
                    page.locator(".chat-home-recent").wait_for()
                    page.locator(".clean-recent").first.get_by_role("button",name="全部",exact=True).click()
                    page.locator("#workspace-navigation").get_by_label("搜索会话").wait_for()
                    page.locator("#workspace-navigation").get_by_label("记录类型").select_option("work")
                    expect(page.locator("#workspace-navigation").get_by_text(demo_chat["title"],exact=True)).to_have_count(0)
                    page.locator("#workspace-navigation").get_by_label("记录类型").select_option("all")
                    page.locator("#workspace-navigation").get_by_label("会话范围").select_option("archived")
                    page.locator("#workspace-navigation").get_by_text("暂无已归档会话").wait_for()
                    assert page.locator(".chat-history").count()==0
                    page.locator(".clean-recent").first.get_by_role("button",name="收起",exact=True).click()
                if name=="29-overview":
                    page.wait_for_url("**/")
                    assert page.locator(".workflow-step").count()==0
                    assert page.locator("#workspace-navigation").get_by_role("link",name="首页",exact=True).count()==0
                if name=="12-create":
                    page.wait_for_url("**/project/creation")
                    page.locator(".project-hub").get_by_role("heading",name="教学制作",exact=True).wait_for()
                    expect(page.locator(".project-hub .project-link")).to_have_count(4)
                    expect(page.locator(".production-grid .production-video")).to_have_count(1)
                    expect(page.locator(".production-grid .production-document")).to_have_count(3)
                    expect(page.locator(".production-library")).to_have_attribute("href","/teaching-library")
                    page.locator("#workspace-navigation").get_by_role("link",name="教学教研",exact=True).click()
                    page.wait_for_url("**/project/teaching")
                    page.locator(".project-hub").get_by_role("heading",name="教学教研",exact=True).wait_for()
                    expect(page.locator(".project-hub .project-link")).to_have_count(5)
                    for label in ("题库","知识库","知识图谱","来源库"):
                        expect(page.locator(".project-hub").get_by_role("link",name=label,exact=True)).to_be_visible()
                    assert page.locator(".project-hub").get_by_role("link",name="视频制作",exact=True).count()==0
                    page.locator("#workspace-navigation").get_by_role("link",name="资料录入",exact=True).click()
                    page.wait_for_url("**/intake")
                    page.locator(".manual-new").wait_for()
                    expect(page.locator(".project-hub")).to_have_count(0)
                    assert page.locator(".topbar .breadcrumb strong").evaluate("el=>getComputedStyle(el).color") == "rgb(48, 69, 58)"
                    visit(page,"/project/intake",".manual-new")
                    page.wait_for_url("**/intake")
                    page.locator("#workspace-navigation").get_by_role("link",name="教学制作",exact=True).click()
                    page.wait_for_url("**/project/creation")
                    page.locator(".project-hub").get_by_role("heading",name="教学制作",exact=True).wait_for()
                    for label in ("视频制作","组卷","组讲义","组教材"):
                        expect(page.locator(".project-hub").get_by_role("link",name=label,exact=True)).to_be_visible()
                    nav=page.locator("#workspace-navigation")
                    nav.get_by_role("button",name="展开教学制作",exact=True).click()
                    expect(nav.get_by_role("link",name="组卷",exact=True)).to_be_visible()
                    nav.get_by_role("button",name="收起教学制作",exact=True).click()
                    expect(nav.get_by_role("link",name="组卷",exact=True)).to_have_count(0)
                    page.locator("#workspace-navigation").get_by_role("link",name="内容发布",exact=True).click()
                    page.wait_for_url("**/project/publishing")
                    page.locator(".project-hub").get_by_role("heading",name="内容发布",exact=True).wait_for()
                    expect(page.locator(".project-hub .project-link")).to_have_count(2)
                    expect(page.locator(".project-hub").get_by_role("link",name="封面设计",exact=True)).to_be_visible()
                    expect(page.locator(".project-hub").get_by_role("link",name="作品管理",exact=True)).to_be_visible()
                    page.locator("#workspace-navigation").get_by_role("link",name="商品售卖",exact=True).click()
                    page.wait_for_url("**/project/sales")
                    page.locator(".project-hub").get_by_role("heading",name="商品售卖",exact=True).wait_for()
                    page.locator(".project-hub").get_by_role("link",name="商品售卖",exact=True).click()
                    page.get_by_text("商品上架",exact=True).wait_for()
                    assert page.locator(".module-hub").get_by_role("link",name="教学作品",exact=True).count()==0
                    visit(page,"/create",".project-hub .project-link")
                    assert page.locator(".clean-context-menu").count()==0
                if name=="13-video":
                    expect(page.locator(".video-stage-track")).to_have_count(0)
                    expect(page.locator(".video-project-pages")).to_have_count(0)
                    expect(page.get_by_role("button",name="＋ 新建视频",exact=True)).to_be_visible()
                    expect(page.get_by_label("推理强度",exact=True)).to_have_count(0)
                    video_test_enabled=True
                    video_jobs.clear()
                    try:
                        visit(page,"/videos",".video-new-card")
                        page.get_by_role("button",name="＋ 新建视频",exact=True).click()
                        page.locator(".video-question-row").first.click()
                        expect(page.locator(".video-pick-preview .katex").first).to_be_visible()
                        page.get_by_role("button",name="确认题目，下一步",exact=True).click()
                        effort=page.locator(".video-settings").get_by_label("推理强度",exact=True)
                        expect(effort).to_be_enabled()
                        expect(page.locator(".video-stage-track > div")).to_have_count(5)
                        effort.select_option("high")
                        assert effort.input_value()=="high"
                        start=page.get_by_role("button",name="开始制作视频",exact=True)
                        expect(start).to_be_enabled()
                        with page.expect_request(lambda req:req.url.endswith("/video-preview/generate") and req.method=="POST") as sent:
                            start.click()
                        assert sent.value.post_data_json=={"effort":"high","model":"Auto"}
                        expect(page.locator(".real-progress")).to_have_text("37%")
                        expect(page.get_by_role("button",name="查看源码",exact=True)).to_have_count(0)
                        video_jobs[0].pop("overall")
                        expect(page.get_by_text("引擎未提供准确百分比",exact=True)).to_be_visible(timeout=10000)
                        expect(page.locator(".real-progress")).to_have_count(0)
                    finally:
                        video_test_enabled=False
                        video_jobs.clear()
                if name=="02-bank":
                    page.get_by_role("button",name="高级筛选").click()
                    expect(page.get_by_label("章节",exact=True)).to_be_visible()
                    # Existing API multi-source filter, not a simulated client-side filter.
                    picker=page.locator(".resource-multi").filter(has_text="具体来源")
                    picker.locator("summary").click()
                    checkbox=picker.get_by_role("checkbox").first
                    expect(checkbox).to_be_visible()
                    with page.expect_request(lambda req:"/api/resources?" in req.url and "source_ids=" in req.url):
                        checkbox.check()
                    expect(picker).to_contain_text("已选 1 项")
                    page.get_by_label("起始年份",exact=True).fill("2010")
                    page.get_by_label("结束年份",exact=True).fill("2025")
                    page.get_by_label("内容完整性",exact=True).select_option("missing_answer")
                    with page.expect_request(lambda req:"/api/resources?" in req.url and "year_from=2010" in req.url and "integrity=missing_answer" in req.url):
                        page.get_by_role("button",name="应用筛选",exact=True).click()
                    expect(page.locator(".question-bank-active-filters")).to_contain_text("2010")
                    page.get_by_role("button",name="重置",exact=True).click()
                    page.get_by_role("button",name="收起筛选").click()
                    page.locator(".bank-detail .katex").first.wait_for()
                    expect(page.locator(".question-bank-row").first).to_contain_text("2份来源")
                    expect(page.locator(".question-bank-row").first).to_contain_text("2种解法")
                    page.get_by_role("button",name="批量管理",exact=True).click()
                    page.get_by_role("checkbox",name="全选本页").check()
                    expect(page.locator(".question-bank-selection")).to_contain_text("已选 4 道")
                    page.get_by_role("button",name="取消选择",exact=True).click()
                    expect(page.locator(".question-bank-selection")).to_contain_text("已选 0 道")
                    # Inline limit notation uses an under-script, not a side subscript.
                    assert page.locator(".bank-list .katex .op-limits").count()>0
                    assert page.locator(".bank-list .katex").count()>0
                    assert page.locator(".bank-detail details:not(:first-child)[open]").count()==0
                    page.locator(".bank-row").first.hover()
                    expect(page.get_by_role("dialog",name="资源悬停预览")).to_be_visible()
                    assert page.locator(".resource-hover-preview details[open]").count()==0
                    page.keyboard.press("Escape")
                    expect(page.get_by_role("dialog",name="资源悬停预览")).to_have_count(0)
                    page.get_by_role("checkbox",name="选择 QDEMO0001").check()
                    page.get_by_role("button",name="批量操作",exact=True).click()
                    page.get_by_role("button",name="预览调整难度",exact=True).click()
                    expect(page.locator(".bank-bulk-counts")).to_contain_text("可执行 1")
                    page.get_by_role("button",name="返回题库",exact=False).click()
                    page.get_by_role("button",name="取消选择",exact=True).click()
                    page.get_by_role("checkbox",name="选择 QDEMO0001").check()
                    page.get_by_role("button",name="加入选题清单",exact=True).first.click()
                    expect(page.locator(".bank-cart-item")).to_have_count(1)
                    page.get_by_role("button",name="返回题库",exact=False).click()
                    page.get_by_role("button",name="选题清单",exact=True).click()
                    expect(page.locator(".bank-cart-item")).to_have_count(1)
                    page.locator(".bank-tool-actions select").select_option("video")
                    page.get_by_role("button",name="确认选题",exact=True).click()
                    with page.expect_request(lambda req:req.url.endswith("/video/projects") and req.method=="POST") as queued_video:
                        page.get_by_role("button",name="加入视频项目队列（1）",exact=True).click()
                    assert queued_video.value.post_data_json["resource_id"]==items[0]["id"]
                    page.locator(".video-work").wait_for()
                if name=="25-word-ai":
                    page.locator(".manual-word-work").wait_for()
                    expect(page.locator(".manual-word-matches")).to_have_count(0)
                    assert page.get_by_role("button",name="批量审核入库").count()==0
                    assert page.get_by_role("button",name="AI协作",exact=True).count()==0
                    assert page.get_by_role("button",name="原文",exact=True).count()==0
                    assert page.get_by_role("link",name="AI 录入",exact=True).count()==0
                    expect(page.locator(".manual-word-paper")).to_have_count(1)
                    expect(page.locator(".manual-word-editor")).to_have_count(0)
                    page.get_by_role("button",name="编辑 第 1 题",exact=True).click()
                    page.get_by_label("题目",exact=True).fill(r"测试查重 $x^2$ 与 $y^2$")
                    page.get_by_label("难度",exact=True).click()
                    tokens=page.get_by_label("题目",exact=True).locator(".inline-math-token")
                    expect(tokens).to_have_count(2)
                    tokens.nth(1).evaluate("(el)=>el.dataset.localRenderProbe='unchanged'")
                    tokens.nth(0).click()
                    page.get_by_label("编辑 LaTeX 公式",exact=True).fill("$x^3$")
                    page.get_by_label("难度",exact=True).click()
                    expect(tokens.nth(0)).to_have_attribute("data-math-source","$x^3$")
                    expect(tokens.nth(1)).to_have_attribute("data-local-render-probe","unchanged")
                    page.locator(".manual-word-matches").get_by_text("相似度 80.0%",exact=False).wait_for()
                    expect(page.locator(".manual-word-matches .manual-match")).to_have_count(2)
                    page.locator(".manual-word-paper-tail").first.click()
                    expect(page.locator(".manual-word-editor")).to_have_count(0)
                    expect(page.locator(".manual-word-paper .manual-word-stem .katex").first).to_be_visible()
                    expect(page.locator(".manual-word-paper .manual-word-stem").first.locator(".katex")).to_have_count(2)
                    page.get_by_role("button",name="编辑 第 1 题",exact=True).click()
                    expect(page.get_by_label("题目",exact=True).locator(".inline-math-token").nth(0)).to_have_attribute("data-math-source","$x^3$")
                    # Clicking a non-interactive area outside the canvas must also collapse.
                    page.locator(".manual-word-outline .manual-word-side-head").click()
                    expect(page.locator(".manual-word-editor")).to_have_count(0)
                    page.get_by_role("button",name="编辑 第 1 题",exact=True).click()
                    expect(page.get_by_label("题目",exact=True).locator(".inline-math-token").nth(0)).to_have_attribute("data-math-source","$x^3$")
                    page.locator(".manual-word-matches .manual-word-side-head").first.click()
                    expect(page.locator(".manual-word-editor")).to_have_count(0)
                    page.get_by_role("button",name="编辑 第 1 题",exact=True).click()
                    page.locator(".manual-word-editor").get_by_role("button",name="移除",exact=True).click()
                    expect(page.get_by_role("dialog",name="移除条目")).to_be_visible()
                    page.get_by_role("dialog",name="移除条目").get_by_role("button",name="取消",exact=True).click()
                    expect(page.locator(".manual-word-editor")).to_have_count(1)
                    # Clipboard image is stored as a safe attachment token, with editable width.
                    stem=page.get_by_label("题目",exact=True)
                    stem.evaluate("""el=>{el.focus();const range=document.createRange();range.selectNodeContents(el);range.collapse(false);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);const data=new DataTransfer();data.items.add(new File([new Uint8Array([137,80,78,71])],"paste.png",{type:"image/png"}));el.dispatchEvent(new ClipboardEvent("paste",{clipboardData:data,bubbles:true,cancelable:true}));}""")
                    image=stem.locator(".inline-image-token")
                    expect(image).to_have_count(1)
                    expect(image).to_have_attribute("data-image-source","[[img:12345678-1234-4321-8765-123456789abc:50]]")
                    image.get_by_role("button",name="图片宽度 75%",exact=True).click()
                    expect(image).to_have_attribute("data-image-source","[[img:12345678-1234-4321-8765-123456789abc:75]]")
                    page.get_by_role("button",name="完成编辑",exact=True).click()
                    expect(page.locator(".manual-word-editor")).to_have_count(0)
                    expect(page.locator(".manual-word-read .stored-inline-image img")).to_have_count(1)
                    page.get_by_role("button",name="整套预览",exact=True).click()
                    page.locator(".manual-intake-preview .katex").first.wait_for()
                    capture(page,path=str(OUT/"25-word-intake-preview.png"),full_page=False)
                    page.get_by_role("button",name="编辑",exact=True).click()
                    with page.expect_request(lambda req:req.url.endswith("/documents/ai-demo/manual-draft") and req.method=="PUT") as saved_image:
                        page.get_by_role("button",name="保存草稿",exact=True).click()
                    assert "[[img:12345678-1234-4321-8765-123456789abc:75]]" in saved_image.value.post_data_json["blocks"][0]["content"]
                    page.get_by_text("草稿已保存，尚未入库",exact=True).wait_for()
                if name=="04-word":
                    page.locator(".manual-word-work .katex").first.wait_for()
                    outline=page.locator(".manual-word-outline nav button")
                    assert outline.count()==4
                    outline.first.click()
                    expect(page.locator(".manual-word-item.active")).to_have_count(1)
                    outline.first.click()
                    expect(page.locator(".manual-word-editor")).to_have_count(0)
                    outline.first.click()
                    expect(page.locator(".manual-word-editor")).to_have_count(1)
                    page.get_by_role("button",name="微调原题 / 知识点",exact=True).click()
                    page.get_by_role("dialog").get_by_role("button",name="确认",exact=True).click()
                    page.get_by_label("题目",exact=True).locator(".inline-math-token").first.wait_for()
                    page.get_by_role("button",name="取消微调",exact=True).click()
                    page.get_by_role("button",name="下移",exact=True).click()
                    assert outline.nth(1).get_attribute("aria-current")=="true"
                    page.get_by_role("button",name="上移",exact=True).click()
                    assert outline.first.get_attribute("aria-current")=="true"
                    page.get_by_role("button",name="整套预览",exact=True).click()
                    expect(page.locator(".manual-intake-preview .print-question-number")).to_have_count(4)
                    page.get_by_role("button",name="编辑",exact=True).click()
                    page.set_viewport_size({"width":393,"height":873})
                    page.get_by_role("button",name="编辑第 1 个条目",exact=True).click()
                    page.locator(".mobile-doc-card").wait_for()
                    page.locator(".manual-render .katex").first.wait_for()
                    assert page.locator(".manual-word-canvas").count()==0
                    assert page.get_by_role("button",name="AI 修改",exact=True).count()==0
                    assert page.get_by_role("button",name="原文对照",exact=True).count()==0
                    assert page.get_by_role("link",name="导出 PDF",exact=True).count()==0
                    page.get_by_role("button",name="下一条",exact=True).click()
                    assert page.locator(".mobile-doc-card h2").inner_text()=="第 2 题"
                    page.get_by_role("button",name="录入编辑",exact=True).click()
                    expect(page.locator(".manual-list-row")).to_have_count(4)
                    page.get_by_role("button",name="Word 预览",exact=True).click()
                    assert page.locator(".manual-intake-preview .katex").count()>0
                    page.get_by_role("button",name="录入编辑",exact=True).click()
                    page.get_by_role("button",name="编辑第 1 个条目",exact=True).click()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    capture(page,path=str(OUT/"27-mobile-card.png"),full_page=False)
                    page.get_by_role("button",name="切换 Word 版").click()
                    expect(page.locator(".manual-word-canvas")).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    capture(page,path=str(OUT/"24-word-mobile.png"),full_page=False)
                    page.set_viewport_size({"width":1600,"height":900})
                    page.get_by_role("button",name="保存草稿",exact=True).click()
                    page.get_by_text("草稿已保存，尚未入库",exact=True).wait_for()
                if name=="06-cover":
                    # Freeform canvas: mathematical layers remain rendered while editing.
                    page.get_by_role("button",name="＋ 公式",exact=True).click()
                    page.locator(".fc-art .katex").first.wait_for()
                    page.get_by_label("LaTeX 源码",exact=True).fill(r"\lim\limits_{x\to0}\frac{\sin x}{x}")
                    page.locator(".fc-art .katex .op-limits").first.wait_for()
                    page.get_by_role("button",name="＋ 文字",exact=True).click()
                    page.get_by_label("内容（支持 LaTeX）",exact=True).fill("极限计算")
                    page.get_by_label("Y",exact=True).fill("100")
                    assert page.locator(".fc-art > div").count()==2
                    page.locator(".fc-toolbar").get_by_role("button",name="多选",exact=True).click()
                    # Multi-select adds the formula to the currently selected text.
                    page.locator(".fc-layer-name").filter(has_text="公式").click()
                    expect(page.get_by_text("已选 2 个元素",exact=True)).to_be_visible()
                    page.get_by_role("button",name="左对齐",exact=True).click()
                    positions=page.locator(".fc-art > div").evaluate_all("(els)=>els.map(e=>parseFloat(e.style.left))")
                    assert abs(positions[0]-positions[1])<=1
                    page.get_by_role("button",name="组合",exact=True).click()
                    page.get_by_role("button",name="取消组合",exact=True).click()
                    page.get_by_role("button",name="撤销",exact=True).click()
                    page.get_by_role("button",name="重做",exact=True).click()
                    for variant,w,h in [
                        ("bilibili",1200,900),("bilibili_wide",1920,1080),
                        ("douyin",1080,1440),("douyin_wide",1440,1080),("douyin_full",1080,1920),
                        ("xiaohongshu",1080,1440),("wechat_top",900,383),("wechat_sub",500,500)
                    ]:
                        page.get_by_label("画布比例",exact=True).select_option(variant)
                        expect(page.get_by_text(f"{w} × {h}",exact=True)).to_be_visible()
                        assert page.locator(".fc-art").evaluate("(el)=>[el.offsetWidth,el.offsetHeight]")==[w,h]
                        assert page.locator(".fc-art .katex").count()>0
                        assert page.locator(".fc-art .fc-guide,.fc-art .fc-snap,.fc-art .fc-hit").count()==0
                    # Native-size PNG, using one clean formula and a known geometry.
                    page.locator(".fc-inspector").get_by_role("button",name="删除",exact=True).click()
                    page.get_by_label("画布比例",exact=True).select_option("wechat_sub")
                    page.get_by_role("button",name="＋ 公式",exact=True).click()
                    page.locator(".fc-art .katex").first.wait_for()
                    # Give the fraction enough room for its display math line box.
                    page.get_by_label("高度",exact=True).fill("200")
                    page.get_by_label("Y",exact=True).fill("100")
                    page.get_by_label("字号",exact=True).fill("24")
                    import struct
                    with page.expect_download(timeout=60000) as downloaded:
                        page.get_by_role("button",name="导出 PNG",exact=True).click()
                    with open(downloaded.value.path(),"rb") as png:
                        header=png.read(24)
                    assert header[:8]==bytes.fromhex("89504e470d0a1a0a")
                    assert struct.unpack(">II",header[16:24])==(500,500)
                    # Touch-sized bottom toolbar and drawer are independent of desktop panels.
                    page.set_viewport_size({"width":390,"height":844})
                    tools=page.get_by_role("navigation",name="手机封面工具")
                    expect(tools).to_be_visible()
                    # At fit zoom the entire canvas stays above the bottom controls.
                    page.get_by_role("button",name="适应画布",exact=True).click()
                    assert page.locator(".fc-art").evaluate("(el)=>{const b=el.getBoundingClientRect(),v=document.querySelector('.fc-viewport').getBoundingClientRect();return b.top>=v.top-1&&b.bottom<=v.bottom+1&&b.left>=v.left-1&&b.right<=v.right+1}")
                    assert page.locator(".fc-toolbar").evaluate("(el)=>el.getBoundingClientRect().height<=48")
                    page.get_by_role("button",name="更多封面操作",exact=True).click()
                    expect(page.get_by_role("button",name="存为模板",exact=True)).to_be_visible()
                    page.get_by_role("button",name="更多封面操作",exact=True).click()
                    tools.get_by_role("button",name="图层",exact=True).click()
                    expect(page.locator(".fc-add")).to_be_visible()
                    page.locator(".fc-add").get_by_role("button",name="完成",exact=True).click()
                    expect(page.locator(".fc-add")).not_to_be_visible()
                    tools.get_by_role("button",name="属性",exact=True).click()
                    expect(page.locator(".fc-inspector")).to_be_visible()
                    page.locator(".fc-inspector").get_by_role("button",name="完成",exact=True).click()
                    expect(page.locator(".fc-inspector")).not_to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth+2")
                    page.set_viewport_size({"width":1440,"height":900})

                capture(page,path=str(OUT/(name+".png")),full_page=False)
        if GROUP in {'all','desktop','mobile'}:
            print('UI case: source statistics scope and distribution on both screen sizes',flush=True)
            page.set_viewport_size({"width":393,"height":873} if GROUP=="mobile" else {"width":1600,"height":900})
            stats_requests=[]
            def stats_api(route):
                endpoint=route.request.url.split("/statistics",1)[1].split("?",1)[0]
                if endpoint=="/scopes":
                    route.fulfill(json={"items":[]});return
                body=route.request.post_data_json
                stats_requests.append((endpoint,body))
                assert body["years"]==["2026"] and body["institutions"]==["郑州大学"]
                if endpoint=="/distribution":
                    name={"question_type":"综合题","method":"泰勒展开","cooccurrence":"极限运算"}[body["dimension"]]
                    if body["dimension"]=="cooccurrence":
                        assert body["knowledge_name"]=="重要极限" and body["knowledge_subject"]=="高等数学"
                    result={"question_count":2,"classified_questions":1,"total":1,"limit":30,"offset":0,"items":[{"subject":"高等数学","name":name,"question_count":1,"source_question_count":2}]}
                elif endpoint=="/questions":
                    assert body["knowledge_name"]=="重要极限"
                    result={"total":1,"limit":30,"offset":0,"items":[{"id":items[0]["id"],"code":items[0]["code"],"title":items[0]["title"],"subject":"高等数学","question_type":"综合题","source_count":2,"revision":1}]}
                else:
                    assert endpoint==""
                    result={"source_count":2,"confirmed_complete_sources":0,"question_count":2,"source_question_count":3,"questions_with_knowledge":2,"knowledge_count":1,"limit":50,"offset":0,"items":[{"subject":"高等数学","name":"重要极限","question_count":1,"source_question_count":2}]}
                route.fulfill(json=result)
            statistics_route=re.compile(r".*/api/source-catalog/statistics(?:/[^?]*)?(?:\?.*)?$")
            page.route(statistics_route,stats_api)
            visit(page,"/source-catalog/statistics",".source-statistics")
            page.get_by_placeholder("2026，2025",exact=True).fill("2026")
            page.get_by_placeholder("郑州大学",exact=True).fill("郑州大学")
            page.get_by_role("button",name="开始统计",exact=True).click()
            expect(page.get_by_role("heading",name="统计结果",exact=True)).to_be_visible()
            page.get_by_role("button",name="重要极限",exact=True).click()
            expect(page.get_by_role("heading",name="重要极限 · 关联题目")).to_be_visible()
            expect(page.get_by_text(items[0]["code"],exact=False).last).to_be_visible()
            page.get_by_role("button",name="关闭",exact=True).click()
            for dimension,button_name,expected in (("question_type","题型分布","综合题"),("method","解析中的方法名称","泰勒展开"),("cooccurrence","知识点共现","极限运算")):
                page.get_by_role("button",name=button_name,exact=True).click()
                if dimension=="cooccurrence":
                    expect(page.get_by_role("button",name="生成分布",exact=True)).to_be_disabled()
                    page.get_by_label("选择指定知识点").select_option(label="高等数学 · 重要极限")
                page.get_by_role("button",name="生成分布",exact=True).click()
                expect(page.get_by_role("cell",name=expected,exact=True)).to_be_visible()
            assert [x[0] for x in stats_requests]==["","/questions","/distribution","/distribution","/distribution"]
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            capture(page,path=str(OUT/("f43-statistics-"+GROUP+".png")),full_page=False)
            page.unroute(statistics_route,stats_api)
        if GROUP in {'all','desktop','mobile'}:
            print('UI case: persisted agent workflow and confirmed advance',flush=True)
            page.set_viewport_size({"width":393,"height":873} if GROUP=="mobile" else {"width":1600,"height":900})
            visit(page,"/work?workspace=agent-work-demo",".agent-workflow")
            expect(page.get_by_label("实际工作进度")).to_contain_text("已识别 5/5")
            expect(page.get_by_text("先识别旧教材",exact=True)).to_be_visible()
            expect(page.get_by_label("继续识别指令")).to_be_visible()
            expect(page.locator(".agent-manual")).to_have_count(0)
            page.get_by_role("button",name="资料与识别").first.click()
            expect(page.locator(".agent-manual")).to_be_visible()
            page.locator(".agent-manual").get_by_role("button",name="收起",exact=True).click()
            page.get_by_role("button",name="添加资料",exact=True).click()
            expect(page.get_by_role("group",name="资料工具")).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.get_by_role("group",name="资料工具")).to_have_count(0)
            expect(page.get_by_role("button",name="按计划继续 AI 整理",exact=True)).to_be_enabled()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            capture(page,path=str(OUT/("31-agent-work-mobile.png" if GROUP=="mobile" else "31-agent-work-desktop.png")),full_page=False)
            with page.expect_request(lambda req:req.url.endswith("/agent/advance") and req.method=="POST") as advanced:
                page.get_by_role("button",name="按计划继续 AI 整理",exact=True).click()
            assert advanced.value.post_data_json["plan_id"]=="agent-plan"
            page.locator(".wg-work-result").first.wait_for()
            assert "fromWorkspace=agent-work-demo" in page.url
            page.get_by_role("link",name="返回资料工作").click()
            expect(page.get_by_label("实际工作进度")).to_be_visible()
            visit(page,"/work?job=review-agent-match&review=1&fromWorkspace=agent-work-demo",".agent-reference-match")
            expect(page.locator(".agent-reference-match")).to_contain_text("匹配字段：答案")
            expect(page.get_by_label("计划参考批次")).to_have_value("reference-batch")
            expect(page.get_by_role("button",name="按计划开始参考匹配",exact=True)).to_be_enabled()
            with page.expect_request(lambda req:req.url.endswith("/agent/matching") and req.method=="POST") as matched:
                page.get_by_role("button",name="按计划开始参考匹配",exact=True).click()
            assert matched.value.post_data_json["source_batch_id"]=="reference-batch"
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        if GROUP in {'all','desktop','mobile'}:
            print('UI case: chaptered textbook on desktop and mobile',flush=True)
            page.set_viewport_size({"width":393,"height":873} if GROUP=="mobile" else {"width":1600,"height":900})
            book_kind="handout" if GROUP=="mobile" else "textbook"
            book={**doc,"id":"book-preview","title":"分章教学资料测试","kind":book_kind,"chaptered":True,"source_id":None,"blocks":[],"revision":3}
            chapter={**doc,"id":"chapter-preview","title":"第一章 极限","kind":book_kind,"chaptered":False,"parent_document_id":book["id"],"source_id":None,"blocks":[{**doc["blocks"][0],"uid":"chapter-question"}],"revision":1}
            directory=[{"id":chapter["id"],"title":chapter["title"],"revision":1,"chapter_order":1,"archived":False,"updated_at":1,"blocks_count":1}]
            book_requests=[]
            def book_api(route):
                endpoint=route.request.url.split("/api/documents/",1)[1].split("?",1)[0]
                book_requests.append((route.request.method,endpoint))
                if endpoint=="book-preview/chapters":
                    if route.request.method=="POST":
                        body=route.request.post_data_json
                        assert body["revision"]==book["revision"]
                        book["revision"]+=1
                        directory.append({"id":"second-chapter","title":body["title"],"revision":1,"chapter_order":2,"archived":False,"updated_at":1,"blocks_count":0})
                    result={"document":{k:v for k,v in book.items() if k!="blocks"},"items":directory}
                elif endpoint=="book-preview/versions":
                    result={"items":[{"revision":book["revision"],"title":book["title"],"created_at":1,"blocks_count":1,"chapter_count":len(directory),"current":True}]}
                elif endpoint=="book-preview":result=book
                elif endpoint=="chapter-preview":
                    if route.request.method=="PUT":
                        body=route.request.post_data_json
                        assert body["parent_document_id"]==book["id"]
                        chapter.update(body,revision=chapter["revision"]+1)
                        directory[0].update(blocks_count=len(chapter["blocks"]),revision=chapter["revision"])
                        book["revision"]+=1
                    result=chapter
                elif endpoint=="chapter-preview/export":result=chapter
                else:raise AssertionError(endpoint)
                route.fulfill(json=result)
            book_route=re.compile(r".*/api/documents/(?:book-preview|chapter-preview)(?:/[^?]*)?(?:[?].*)?$")
            page.route(book_route,book_api)
            visit(page,("/handouts" if book_kind=="handout" else "/textbooks")+"?doc=book-preview",".chaptered-book")
            expect(page.locator(".book-chapter-row")).to_have_count(1)
            assert ("GET","chapter-preview") not in book_requests
            page.get_by_label("新章节名称").fill("第二章 导数")
            page.get_by_role("button",name="＋ 新增章节",exact=True).click()
            expect(page.locator(".book-chapter-row")).to_have_count(2)
            if os.environ.get("WG_BOOK_SCREENSHOTS")=="1":
                page.evaluate("document.fonts.ready")
                page.screenshot(path=str(OUT/("f44-directory-"+GROUP+".png")),full_page=False)
                if GROUP=="desktop":
                    page.set_viewport_size({"width":393,"height":873})
                    page.screenshot(path=str(OUT/"f44-textbook-directory-phone.png"),full_page=False)
                    page.set_viewport_size({"width":1600,"height":900})
            page.get_by_role("button",name="编辑本章",exact=True).first.click()
            page.locator(".manual-intake-cards").wait_for()
            assert ("GET","chapter-preview") in book_requests
            if os.environ.get("WG_BOOK_SCREENSHOTS")=="1":
                page.evaluate("document.fonts.ready")
                page.screenshot(path=str(OUT/("f44-chapter-"+GROUP+".png")),full_page=False)
            expect(page.get_by_role("button",name="＋ 章",exact=True)).to_have_count(0)
            if GROUP=="mobile":
                page.get_by_role("button",name="＋ 添加内容",exact=True).click()
            page.get_by_role("button",name="＋ 正文",exact=True).click()
            page.get_by_label("正文",exact=True).fill("章节独立保存测试")
            with page.expect_request(lambda req:req.url.endswith("/api/documents/chapter-preview") and req.method=="PUT") as chapter_save:
                page.get_by_role("button",name="保存编排",exact=True).click()
            assert len(chapter_save.value.post_data_json["blocks"])==2
            expect(page.get_by_text("编排已保存到服务器",exact=True)).to_be_visible()
            page.get_by_role("link",name="返回全书目录",exact=False).click()
            expect(page.locator(".book-chapter-row")).to_have_count(2)
            page.get_by_role("button",name="全书版本历史",exact=True).click()
            expect(page.locator(".book-version-list")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+2")
            capture(page,path=str(OUT/("f44-book-"+GROUP+".png")),full_page=False)
            page.unroute(book_route,book_api)
        if GROUP in {'all','editors'}:
            print('UI case: document assembly',flush=True)
            # Compose from the question bank, preserve original resources, and save layout only.
            page.set_viewport_size({"width":1600,"height":900})
            visit(page,"/papers",".assembly-result")
            # Composition-only compatibility selectors must not style an unrelated page.
            assert page.locator(".composition-work .composition-context").evaluate("el=>getComputedStyle(el).display") == "flex"
            assert page.evaluate("""() => { const probe=document.createElement('div'); probe.className='composition-context'; document.querySelector('.content-inner').append(probe); try { return getComputedStyle(probe).display === 'block' } finally { probe.remove() } }""")
            page.locator(".assembly-result").first.wait_for()
            expect(page.locator(".compact-resource-list")).to_be_visible()
            page.locator(".compact-resource-main").first.click()
            expect(page.get_by_role("dialog",name="资源详情")).to_be_visible()
            assert page.locator(".assembly-preview details[open]").count()==0
            page.get_by_role("button",name="关闭详情").click()
            page.get_by_role("button",name="＋ 选入",exact=True).first.click()
            page.get_by_role("button",name="＋ 选入",exact=True).first.click()
            expect(page.locator(".assembly-cart-item")).to_have_count(2)
            page.get_by_label("文档名称",exact=True).fill("组卷测试")
            with page.expect_request(lambda req:req.url.endswith("/api/documents") and req.method=="POST") as created:
                page.get_by_role("button",name="进入 Word 工作台",exact=True).click()
            assert [b["kind"] for b in created.value.post_data_json["blocks"]]==["reference","reference"]
            page.locator(".assembly-word").wait_for()
            assert page.get_by_role("button",name="AI 协作",exact=True).count()==0
            assert page.get_by_role("button",name="批量审核入库",exact=True).count()==0
            expect(page.locator(".manual-word-item")).to_have_count(2)
            expect(page.locator(".manual-word-editor")).to_have_count(0)
            page.get_by_role("button",name="编辑 第 1 题",exact=True).click()
            page.get_by_label("本题分值",exact=True).fill("10")
            page.get_by_role("button",name="下移",exact=True).click()
            page.get_by_role("button",name="＋ 正文",exact=True).click()
            page.get_by_label("正文",exact=True).fill("作答说明")
            page.get_by_role("button",name="整套预览",exact=True).click()
            expect(page.locator(".manual-intake-preview .print-question-number")).to_have_count(2)
            assert page.locator(".manual-intake-preview").get_by_text("作答说明",exact=True).count()>0
            with page.expect_request(lambda req:req.url.endswith("/documents/assembly-demo") and req.method=="PUT") as saved:
                page.get_by_role("button",name="保存编排",exact=True).click()
            assert [b["kind"] for b in saved.value.post_data_json["blocks"]]==["reference","reference","text"]
            assert [b["resource_id"] for b in saved.value.post_data_json["blocks"][:2]]==[items[1]["id"],items[0]["id"]]
            page.get_by_text("编排已保存到服务器",exact=True).wait_for()
            capture(page,path=str(OUT/"30-assembly-paper.png"),full_page=False)
            page.get_by_role("button",name="批量编排",exact=True).click()
            batch_panel=page.locator(".composition-batch")
            batch_panel.get_by_role("button",name="选择当前结果",exact=True).click()
            batch_panel.get_by_label("批量分值").fill("6")
            batch_panel.get_by_role("button",name="设置分值",exact=True).click()
            page.get_by_role("button",name="撤销",exact=True).click()
            page.get_by_role("button",name="重做",exact=True).click()
            with page.expect_request(lambda req:req.url.endswith("/documents/assembly-demo") and req.method=="PUT",timeout=10000) as auto_saved:
                batch_panel.get_by_role("button",name="隐藏答案解析",exact=True).click()
            auto_blocks=auto_saved.value.post_data_json["blocks"]
            assert [b["score"] for b in auto_blocks if b["kind"]=="reference"]==[6,6]
            assert all(b["hidden_fields"]==["answer","solution","analysis","proof"] for b in auto_blocks if b["kind"]=="reference")
            expect(page.get_by_role("button",name="保存编排",exact=True)).to_be_disabled()
            for route in ("handouts","textbooks"):
                visit(page,"/"+route,".assembly-picker")
                page.locator(".assembly-picker").wait_for()
                expect(page.get_by_role("button",name="知识库",exact=True)).to_be_visible()

        if GROUP in {'all','mobile'}:
            print('UI case: compact phone composition and production navigation',flush=True)
            page.set_viewport_size({"width":393,"height":873})
            visit(page,"/work?job=review-clean&review=1",".wg-review-editor .katex")
            expect(page.get_by_role("button",name="通过并继续",exact=True)).to_be_enabled()
            expect(page.get_by_role("button",name="确认生成录入文档",exact=True)).to_be_disabled()
            expect(page.locator(".wg-review-source")).to_be_visible()
            expect(page.locator(".wg-review-editor")).to_be_visible()
            page.get_by_role("button",name="原始资料",exact=True).click()
            expect(page.locator(".wg-review-source")).to_be_visible()
            expect(page.locator(".wg-review-editor")).not_to_be_visible()
            page.get_by_role("button",name="识别结果",exact=True).click()
            page.get_by_role("button",name="通过并继续",exact=True).click()
            expect(page.get_by_role("button",name="确认生成录入文档",exact=True)).to_be_enabled()
            visit(page,"/work?job=review-clean&review=1",".wg-review-editor .katex")
            expect(page.get_by_role("button",name="确认生成录入文档",exact=True)).to_be_enabled()
            page.get_by_role("button",name="修改",exact=True).click()
            page.get_by_label("标题",exact=True).fill("修订后的标题")
            expect(page.get_by_role("button",name="确认生成录入文档",exact=True)).to_be_disabled()
            page.get_by_role("button",name="保存审核",exact=True).click()
            expect(page.get_by_role("button",name="保存审核",exact=True)).to_be_disabled()
            expect(page.locator(".wg-review-footer .workspace-save-state")).to_contain_text("已保存")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.get_by_role("button",name="返回上一步",exact=True).click()
            expect(page.locator(".wg-work-result")).to_be_visible()
            visit(page,"/work?job=review-match&review=1",".wg-review-editor .katex")
            page.get_by_role("button",name="查重结果",exact=True).click()
            expect(page.locator(".wg-review-matches").get_by_text("相似度 80.0%",exact=False)).to_be_visible()
            expect(page.locator(".wg-review-matches .workspace-match-compare").first).to_be_visible()
            expect(page.locator(".wg-review-matches .workspace-match-compare").first).to_contain_text("当前录入")
            expect(page.locator(".wg-review-matches .workspace-match-compare").first).to_contain_text("题库已有资源")
            assert page.locator(".wg-review-matches .manual-match details[open]").count()==0
            expect(page.locator(".wg-review-matches").get_by_role("button",name="使用原题 · 编号不变",exact=True).first).to_be_visible()
            page.get_by_role("button",name="识别结果",exact=True).click()
            page.get_by_role("button",name="通过并继续",exact=True).click()
            expect(page.locator(".wg-review-workbench > .inline-error")).to_contain_text("存在重复候选")
            page.get_by_role("button",name="查重结果",exact=True).click()
            page.locator(".wg-review-matches").get_by_placeholder("例如：条件不同").fill("条件不同，保留独立题目")
            page.get_by_role("button",name="保留当前录入内容",exact=True).click()
            page.get_by_role("button",name="识别结果",exact=True).click()
            page.get_by_role("button",name="通过并继续",exact=True).click()
            expect(page.get_by_role("button",name="确认生成录入文档",exact=True)).to_be_enabled()
            visit(page,"/project/teaching",".project-hub")
            page.get_by_role("button",name="返回上一步",exact=True).click()
            expect(page).to_have_url("http://127.0.0.1:4173"+"/")
            visit(page,"/resources",".bank-workspace")
            page.get_by_role("button",name="返回上一步",exact=True).click()
            expect(page).to_have_url("http://127.0.0.1:4173"+"/project/teaching")
            visit(page,"/videos",".video-new-card")
            page.get_by_role("button",name="＋ 新建视频",exact=True).click()
            expect(page.locator(".video-pick-grid")).to_be_visible()
            page.get_by_role("button",name="返回上一步",exact=True).click()
            expect(page.locator(".video-new-card")).to_be_visible()
            page.get_by_role("button",name="返回上一步",exact=True).click()
            expect(page).to_have_url("http://127.0.0.1:4173"+"/project/creation")
            for route in ("papers","handouts","textbooks"):
                visit(page,"/"+route,".assembly-result")
                expect(page.locator(".doc-selector")).to_have_count(0)
                expect(page.locator(".doc-mode-switch")).to_have_count(0)
                expect(page.locator(".assembly-pages")).to_have_count(0)
                expect(page.locator(".assembly-cart-bar")).to_be_visible()
                assert page.locator(".assembly-cart-bar").evaluate("el=>getComputedStyle(el).position")=="fixed"
                assert page.locator(".assembly-search input").evaluate("el=>el.getBoundingClientRect().height")<=44
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.locator(".compact-resource-main").first.click()
                expect(page.get_by_role("dialog",name="资源详情")).to_be_visible()
                assert page.locator(".assembly-preview details[open]").count()==0
                page.get_by_role("button",name="关闭详情").click()
                page.get_by_role("button",name="＋ 选入",exact=True).first.click()
                page.get_by_role("button",name="查看选题车").click()
                expect(page.locator(".assembly-cart.cart-open")).to_be_visible()
                expect(page.locator(".assembly-cart-item")).to_have_count(1)
                page.locator(".assembly-cart").get_by_role("button",name="清空",exact=True).click()
                page.get_by_role("button",name="关闭选题车").click()
                expect(page.locator(".assembly-cart")).not_to_be_visible()
            print('UI case: phone intake and mobile navigation',flush=True)
            # Phone-first intake: edit formulas in place, navigate without committing, save all at once.
            page.set_viewport_size({"width":393,"height":873})
            visit(page,"/intake?doc=ai-demo",".manual-list-row")
            assert page.locator(".topbar .breadcrumb strong").evaluate("el=>getComputedStyle(el).color") == "rgb(48, 69, 58)"
            assert len(page.locator(".mobile-doc-nav").evaluate("el=>getComputedStyle(el).gridTemplateColumns.split(' ')")) == 2
            page.get_by_role("button",name="编辑第 1 个条目",exact=True).click()
            page.locator(".mobile-doc-card").wait_for()
            page.get_by_label("题目",exact=True).fill(r"求 $\frac{1}{x}$ 的导数。")
            # select_option changes value but does not reliably move keyboard focus.
            # Click outside as a real user would, then assert rendered math.
            page.get_by_label("难度",exact=True).click()
            page.get_by_label("难度",exact=True).select_option("中等")
            page.get_by_label("题目",exact=True).locator(".inline-math-token .katex").wait_for()
            page.get_by_label("题目",exact=True).locator(".inline-math-token").click()
            page.get_by_label("编辑 LaTeX 公式",exact=True).fill(r"$\frac{1}{x^2}$")
            page.get_by_label("难度",exact=True).click()
            page.get_by_label("题目",exact=True).locator(".inline-math-token .katex").wait_for()
            expect(page.get_by_label("编辑 LaTeX 公式",exact=True)).to_have_count(0)
            expect(page.get_by_role("button",name="保存草稿",exact=True)).to_be_enabled()
            expect(page.get_by_label("条目标题",exact=True)).to_have_count(0)
            page.get_by_role("button",name="切换 Word 版").click()
            expect(page.locator(".manual-word-canvas")).to_be_visible()
            assert page.get_by_label("题目",exact=True).locator(".inline-math-token").get_attribute("data-math-source")==r"$\frac{1}{x^2}$"
            page.get_by_role("button",name="切换卡片版").click()
            assert page.get_by_label("题目",exact=True).locator(".inline-math-token").get_attribute("data-math-source")==r"$\frac{1}{x^2}$"
            editor=page.get_by_label("题目",exact=True)
            editor.fill(r"求 $\lim\nolimits_{x\to0}\frac{\sin x}{x}$。")
            editor.blur()
            editor.locator(".inline-math-token .op-limits").wait_for()
            assert editor.locator(".inline-math-token").get_attribute("data-math-source")==r"$\lim\nolimits_{x\to0}\frac{\sin x}{x}$"
            editor.fill(r"求 $\frac{1}{x$。")
            editor.blur()
            expect(editor.locator(".inline-math-invalid")).to_have_attribute("aria-invalid","true")
            assert editor.locator(".inline-math-invalid").get_attribute("data-math-source")==r"$\frac{1}{x$"
            editor.fill(r"求 $\frac{1}{x^2}$ 的导数。")
            editor.blur()
            editor.locator(".inline-math-token .katex").wait_for()

            expect(page.get_by_role("button",name="＋ 选择题",exact=True)).to_have_count(0)
            page.get_by_role("button",name="下一条 · 新增",exact=True).click()
            expect(page.get_by_label("题目",exact=True)).to_have_count(0)
            page.get_by_role("button",name="＋ 选择题",exact=True).click()
            expect(page.get_by_label("科目",exact=True)).to_have_value("")
            page.get_by_label("科目",exact=True).select_option("线性代数")
            page.get_by_label("题目",exact=True).fill("选择正确答案")
            page.get_by_label("A 选项",exact=True).fill("$1$")
            page.get_by_label("B 选项",exact=True).fill("$2$")
            page.locator(".manual-answer-choices").get_by_role("button",name="A",exact=True).click()
            expect(page.get_by_text("正确选项 · 单选题",exact=True)).to_be_visible()
            page.locator(".manual-answer-choices").get_by_role("button",name="B",exact=True).click()
            expect(page.get_by_text("正确选项 · 多选题",exact=True)).to_be_visible()
            page.get_by_role("button",name="下一条 · 新增",exact=True).click()
            page.get_by_role("button",name="＋ 填空题",exact=True).click()
            expect(page.get_by_label("科目",exact=True)).to_have_value("")
            page.get_by_label("科目",exact=True).select_option("概率论与数理统计")
            page.get_by_label("题目",exact=True).fill("计算")
            page.get_by_role("button",name="＋ 插入填空空位",exact=True).click()
            assert "underline" in page.get_by_label("题目",exact=True).locator(".inline-math-token").get_attribute("data-math-source")
            page.get_by_role("button",name="下一条 · 新增",exact=True).click()
            page.get_by_role("button",name="＋ 综合题",exact=True).click()
            page.get_by_label("科目",exact=True).select_option("高等数学")
            page.get_by_label("题目",exact=True).fill("已知函数")
            expect(page.get_by_label("第 1 小问题目",exact=True)).to_have_count(0)
            expect(page.get_by_label("答案",exact=True)).to_be_visible()
            expect(page.get_by_label("解析",exact=True)).to_be_visible()
            page.get_by_label("答案",exact=True).fill("原答案")
            page.get_by_label("解析",exact=True).fill("原解析")
            page.get_by_role("button",name="＋ 添加小问（可选）",exact=True).click()
            page.get_by_role("dialog").get_by_role("button",name="确认",exact=True).click()
            # The dialog close event and React commit occur asynchronously.
            expect(page.get_by_label("第 1 小问题目",exact=True)).to_be_visible()
            expect(page.get_by_label("答案",exact=True)).to_have_count(0)
            expect(page.get_by_label("解析",exact=True)).to_have_count(0)
            expect(page.get_by_label("第 1 小问答案",exact=True)).to_have_text("原答案")
            expect(page.get_by_label("第 1 小问解析",exact=True)).to_have_text("原解析")
            page.get_by_role("button",name="＋ 添加小问（可选）",exact=True).click()
            expect(page.get_by_label("第 2 小问题目",exact=True)).to_be_visible()
            page.locator(".manual-subquestions > .manual-subquestion").nth(1).get_by_role("button",name="移除",exact=True).click()
            expect(page.get_by_label("第 2 小问题目",exact=True)).to_have_count(0)
            page.get_by_label("第 1 小问题目",exact=True).fill("求导数")
            page.get_by_label("第 1 小问答案",exact=True).fill("$2x$")
            page.get_by_label("第 1 小问解析",exact=True).fill("利用导数公式")
            page.get_by_role("button",name="选择已有知识标签",exact=True).click()
            catalog=page.locator(".manual-tag-catalog")
            catalog.locator(".manual-tag-category").wait_for()
            assert catalog.get_by_role("button",name="导数",exact=True).count()==0
            catalog.locator(".manual-tag-category").filter(has_text="微积分").click()
            catalog.get_by_role("button",name="展开 微积分",exact=True).click()
            catalog.get_by_role("button",name="展开 一元函数微分学",exact=True).click()
            catalog.get_by_role("button",name="导数",exact=True).click()
            assert catalog.get_by_role("button",name="定积分",exact=True).count()==0
            page.get_by_label("搜索已有知识标签").fill("定积分")
            catalog.get_by_role("button",name="定积分",exact=False).first.wait_for()

            page.get_by_label("知识标签",exact=True).fill("新知识点")
            page.get_by_role("button",name="新增知识标签",exact=True).click()
            expect(page.get_by_role("button",name="移除知识标签 新知识点",exact=True)).to_be_visible()
            expect(page.get_by_role("button",name="移除知识标签 导数",exact=True)).to_be_visible()
            page.get_by_role("button",name="下一条 · 新增",exact=True).click()
            page.get_by_role("button",name="＋ 综合题",exact=True).click()
            page.get_by_label("题目",exact=True).fill("测试查重")
            page.get_by_role("button",name="使用原题 · 编号不变",exact=True).first.wait_for()
            expect(page.locator(".manual-match")).to_have_count(2)
            expect(page.get_by_text("相似度 80.0%",exact=False)).to_be_visible()
            page.get_by_role("button",name="使用原题 · 编号不变",exact=True).first.click()
            page.get_by_role("dialog").get_by_role("button",name="确认",exact=True).click()
            expect(page.get_by_label("题目",exact=True)).to_have_attribute("contenteditable","false")
            expect(page.get_by_text("已选择原题 QDEMO0002",exact=False)).to_be_visible()
            page.get_by_role("button",name="编辑相关信息 · 另存为新题",exact=True).click()
            expect(page.get_by_label("题目",exact=True)).to_have_attribute("contenteditable","true")
            page.get_by_label("题目",exact=True).fill("修改为新题")
            page.get_by_role("button",name="下一条 · 新增",exact=True).click()
            page.get_by_role("button",name="＋ 章",exact=True).click()
            page.get_by_label("章标题",exact=True).fill("第一章 函数与极限")
            page.get_by_role("button",name="下一条 · 新增",exact=True).click()
            page.get_by_role("button",name="＋ 节",exact=True).click()
            page.get_by_label("节标题",exact=True).fill("第一节 函数")
            page.get_by_role("button",name="Word 预览",exact=True).click()
            expect(page.locator(".manual-intake-preview .print-question-number")).to_have_count(5)
            chapter=page.locator(".manual-intake-preview .print-heading-level-1 h2")
            section=page.locator(".manual-intake-preview .print-heading-level-2 h3")
            assert chapter.inner_text()=="第一章 函数与极限"
            assert section.inner_text()=="第一节 函数"
            assert chapter.evaluate("(e)=>parseFloat(getComputedStyle(e).fontSize)") > section.evaluate("(e)=>parseFloat(getComputedStyle(e).fontSize)") > page.locator(".manual-intake-preview .chat-rich").first.evaluate("(e)=>parseFloat(getComputedStyle(e).fontSize)")
            assert page.locator(".manual-intake-preview .katex").count()>0
            expect(page.get_by_role("button",name="打印 / 保存为 PDF",exact=True)).to_have_count(0)
            expect(page.get_by_text("草稿已保存，尚未入库",exact=True)).to_have_count(0)
            with page.expect_request(lambda req: req.url.endswith("/documents/ai-demo/manual-draft") and req.method=="PUT") as request_info:
                page.get_by_role("button",name="保存草稿",exact=True).click()
            submitted=request_info.value.post_data_json
            assert len(submitted["blocks"])==7
            assert [b["heading_level"] for b in submitted["blocks"] if b["kind"]=="heading"]==[1,2]
            assert submitted["blocks"][0]["difficulty"]=="中等"
            assert submitted["blocks"][1]["question_type"]=="多选题"
            assert submitted["blocks"][1]["subject"]=="线性代数"
            assert submitted["blocks"][2]["subject"]=="概率论与数理统计"
            assert submitted["blocks"][3]["subject"]=="高等数学"
            assert submitted["blocks"][3]["content"]=="已知函数\n(1) 求导数"
            assert submitted["blocks"][3]["answer"]=="(1) $2x$"
            assert submitted["blocks"][3]["solution"]=="(1) 利用导数公式"
            page.get_by_text("草稿已保存，尚未入库",exact=True).wait_for()
            page.get_by_role("button",name="检查并入库",exact=True).click()
            page.get_by_role("heading",name="入库审核",exact=True).wait_for()
            expect(page.get_by_role("button",name="入库预览",exact=True)).to_be_disabled()
            progress=page.locator(".manual-unified-review [role=progressbar]")
            total=int(progress.get_attribute("aria-valuemax"))
            for i in range(total):
                page.get_by_role("button",name="通过并继续",exact=True).click()
                expect(progress).to_have_attribute("aria-valuenow",str(i+1))
            page.get_by_role("button",name="入库预览",exact=True).click()
            page.get_by_role("heading",name="正式入库确认",exact=True).wait_for()
            if page.locator(".manual-review-accept input").count():page.locator(".manual-review-accept input").check()
            page.get_by_role("button",name=re.compile(r"^确认入库 ·")).click()
            page.get_by_role("heading",name="入库成功",exact=True).wait_for()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            capture(page,path=str(OUT/"28-mobile-review.png"),full_page=False)
            page.set_viewport_size({"width":1600,"height":900})
            # Theme and mobile smoke checks use the same compiled application.
            visit(page,"/",".chat-home-recent")
            assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim().toLowerCase()") == "#e8eee8"
            assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar').trim().toLowerCase()") == "#d7e2d9"
            assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--surface').trim().toLowerCase()") == "#f1f5f0"
            assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim().toLowerCase()") == "#52765f"
            page.evaluate("document.documentElement.dataset.theme='dark'")
            assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim().toLowerCase()") == "#1d2733"
            capture(page,path=str(OUT/"09-home-dark.png"),full_page=False)
            page.evaluate("document.documentElement.dataset.theme='light'")
            page.set_viewport_size({"width":393,"height":873})
            capture(page,path=str(OUT/"10-home-mobile.png"),full_page=False)
            expect(page.locator(".mobile-tabs")).to_have_count(0)
            expect(page.get_by_label("输入消息")).to_be_visible()
            expect(page.locator(".clean-chat > .compact-composer")).to_be_visible()
            expect(page.get_by_role("heading",name="今天想研究什么？")).to_be_visible()
            assert page.locator("[data-chat-layout=v3] .compact-composer").evaluate("(el)=>el.getBoundingClientRect().bottom <= innerHeight")
            expect(page.locator(".mode-switch")).to_be_visible()
            for path in ("/chat","/work"):
                visit(page,path,"[data-chat-layout=v3] .compact-composer")
                model_button=page.get_by_role("button",name="打开模型选择",exact=True)
                send_button=page.locator(".compact-tools .composer-send")
                expect(model_button).to_be_visible()
                assert 36<=model_button.evaluate("(el)=>el.getBoundingClientRect().width")<=270
                expect(model_button).to_contain_text("Auto")
                assert page.locator(".compact-tools").evaluate("(el)=>getComputedStyle(el).display")=="flex"
                assert model_button.evaluate("(el)=>el.getBoundingClientRect().right")<=send_button.evaluate("(el)=>el.getBoundingClientRect().left")+1
                model_button.click()
                panel=page.locator(".composer-inference-panel")
                expect(panel).to_be_visible()
                assert panel.evaluate("(el)=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1}")
                assert panel.evaluate("(el)=>el.getBoundingClientRect().bottom")<=model_button.evaluate("(el)=>el.getBoundingClientRect().top")+1
                panel.get_by_role("button",name="高",exact=True).click()
                expect(panel).to_have_count(0)
                expect(model_button).to_contain_text("Auto · 高")
                assert page.locator("#mode-more-panel .reasoning-effort").count()==0
            # Server-reported capabilities, not hardcoded front-end model/effort choices.
            live_models={"source":"cli","models":[{"id":"Auto","label":"Auto","efforts":["medium","high"]}]+[{"id":f"preview-model-{n}","label":f"Preview Model {n}","efforts":["low","xhigh"]} for n in range(7)]}
            refresh_calls=[]
            def live_catalog_route(route):
                route.fulfill(status=200,content_type="application/json",body=json.dumps(live_models))
            def refresh_catalog_route(route):
                refresh_calls.append(route.request.method)
                live_models["models"]=[*live_models["models"],{"id":"new-live-model","label":"New Live Model","efforts":["disabled","low","xhigh"]}]
                route.fulfill(status=200,content_type="application/json",body=json.dumps(live_models))
            context.route("**/api/qoder/models",live_catalog_route)
            context.route("**/api/qoder/models/refresh",refresh_catalog_route)
            try:
                visit(page,"/work","[data-chat-layout=v3] .compact-composer")
                page.get_by_role("button",name="打开模型选择",exact=True).click()
                panel=page.locator(".composer-inference-panel")
                search=panel.get_by_role("searchbox",name="搜索模型")
                expect(search).to_be_visible()
                panel.get_by_role("button",name="刷新模型",exact=True).click()
                search.fill("New Live Model")
                fresh_model=panel.get_by_role("button",name="New Live Model",exact=True)
                expect(fresh_model).to_be_visible()
                assert refresh_calls==["POST"]
                fresh_model.click()
                efforts=panel.get_by_role("group",name="推理强度",exact=True)
                expect(efforts.get_by_role("button",name="极高",exact=True)).to_be_visible()
                expect(efforts.get_by_role("button",name="关闭",exact=True)).to_be_visible()
                expect(efforts.get_by_role("button",name="高",exact=True)).to_have_count(0)
                expect(efforts.get_by_role("button",name="中",exact=True)).to_have_count(0)
                expect(efforts.get_by_role("button",name="默认",exact=True)).to_have_attribute("aria-pressed","true")
                efforts.get_by_role("button",name="极高",exact=True).click()
                expect(panel).to_have_count(0)
                page.get_by_role("button",name="打开模型选择",exact=True).click()
                expect(panel.get_by_role("button",name="New Live Model",exact=True)).to_have_attribute("aria-pressed","true")
                expect(panel.get_by_role("button",name="极高",exact=True)).to_have_attribute("aria-pressed","true")
                page.keyboard.press("Escape")
            finally:
                context.unroute("**/api/qoder/models",live_catalog_route)
                context.unroute("**/api/qoder/models/refresh",refresh_catalog_route)
            visit(page,"/chat",".chat-home-recent")
            page.get_by_role("button",name="添加与工具").click()
            expect(page.get_by_role("group",name="聊天工具")).to_be_visible()
            page.get_by_role("button",name="添加与工具").click()
            expect(page.locator(".workspace > header")).to_have_count(1)
            expect(page.locator(".clean-chat header,.clean-chat .chat-top")).to_have_count(0)
            assert page.get_by_label("输入消息").evaluate("(el) => getComputedStyle(el).borderTopWidth === '0px'")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            menu=page.get_by_role("button",name="打开导航",exact=True)
            menu.click()
            # React commits the drawer state asynchronously; require the open state
            # and visible, actionable navigation before continuing.
            from playwright.sync_api import expect
            expect(menu).to_have_attribute("aria-expanded","true")
            drawer=page.locator("#workspace-navigation.nav.open")
            expect(drawer).to_be_visible()
            expect(drawer.get_by_role("link",name="教学教研",exact=True)).to_be_visible()
            expect(page.locator(".shell > .workspace")).to_have_attribute("inert","")
            drawer.get_by_role("button",name="展开教学教研",exact=True).click()
            expect(drawer.get_by_role("link",name="题库",exact=True)).to_be_visible()
            drawer.get_by_role("button",name="收起教学教研",exact=True).click()
            drawer.get_by_role("link",name="教学教研",exact=True).click()
            page.wait_for_url("**/project/teaching")
            page.locator(".project-hub").get_by_role("heading",name="教学教研",exact=True).wait_for()
            expect(drawer).to_have_count(0)
            expect(page.locator(".project-hub").get_by_role("link",name="来源库",exact=True)).to_be_visible()
            menu.click()
            expect(drawer).to_be_visible()
            drawer.get_by_role("link",name="资料录入",exact=True).click()
            page.wait_for_url("**/intake")
            expect(drawer).to_have_count(0)
            page.locator(".manual-new").wait_for()
            expect(page.locator(".project-hub")).to_have_count(0)
            assert not page.locator(".nav.open").count()
            visit(page,"/sources",".bank-row")
            page.locator(".bank-row").first.click()
            page.get_by_role("link",name="导出 PDF",exact=True).click()
            page.wait_for_url("**/source-print/source-preview")
            expect(page.get_by_role("button",name="打印 / 保存为 PDF",exact=True)).to_have_count(0)
            page.get_by_label("选择排版模板").select_option("paper")
            page.get_by_role("button",name="进入排版工作台",exact=True).click()
            page.locator(".print-document .katex").first.wait_for()
            expect(page.locator(".print-question-number")).to_have_count(4)
            export=page.get_by_role("button",name="打印 / 保存为 PDF",exact=True)
            expect(export).to_be_disabled()
            page.get_by_label("已检查预览，确认无问题").check()
            expect(export).to_be_enabled()
            page.get_by_label("仅题目").check()
            expect(export).to_be_disabled()
            expect(page.locator(".print-document").get_by_text("答案：",exact=False)).to_have_count(0)
            page.get_by_role("button",name="预览",exact=True).click()
            expect(page.locator(".print-document")).to_be_visible()
            expect(page.locator(".layout-settings")).to_have_count(0)
            page.get_by_role("button",name="排版设置",exact=True).click()
            page.get_by_label("纸张",exact=True).select_option("A5")
            page.get_by_role("button",name="保存排版到服务器",exact=True).click()
            expect(page.get_by_role("status").filter(has_text="排版配置已保存到服务器")).to_be_visible()
            page.get_by_label("新模板名称",exact=True).fill("来源测试模板")
            page.get_by_role("button",name="保存为模板",exact=True).click()
            expect(page.get_by_role("status").filter(has_text="模板已保存到服务器")).to_be_visible()
            page.reload(wait_until="networkidle")
            page.get_by_role("button",name="继续上次排版",exact=True).click()
            expect(page.get_by_label("纸张",exact=True)).to_have_value("A5")
            visit(page,"/resources",".bank-row")
            page.locator(".bank-row").first.wait_for()
            expect(page.locator(".bank-detail")).to_be_hidden()
            page.get_by_role("button",name="批量管理",exact=True).click()
            page.get_by_role("checkbox",name="选择 QDEMO0001",exact=True).check()
            expect(page.locator(".question-bank-selection")).to_contain_text("已选 1 道")
            page.locator(".bank-row").first.click()
            page.locator(".bank-detail .katex").first.wait_for()
            expect(page.locator(".bank-list")).to_be_hidden()
            capture(page,path=str(OUT/"30-resource-mobile.png"),full_page=False)
            page.get_by_role("button",name="返回资源列表",exact=False).click()
            expect(page.locator(".bank-list")).to_be_visible()
            expect(page.get_by_role("checkbox",name="选择 QDEMO0001",exact=True)).to_be_checked()
            expect(page.locator(".question-bank-selection")).to_contain_text("已选 1 道")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            visit(page,"/works",".studio-library")
            expect(page.locator(".studio-library")).to_be_visible()
            page.get_by_role("button",name="新建",exact=True).click()
            expect(page.locator(".clean-studio .resource-form")).to_be_visible()
            expect(page.locator(".studio-library")).to_be_hidden()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            # Qoder login must visibly report unavailable services and expose a real
            # authorization link even if the browser blocks automatic popups.
            login_fixture={"available":False,"detail":"执行服务未连接"}
            def login_api(route):
                route.fulfill(status=200,content_type="application/json",body=json.dumps(login_fixture,ensure_ascii=False))
            context.route("**/api/qoder/status",login_api)
            page.goto("http://127.0.0.1:4173/qoder",wait_until="networkidle")
            page.get_by_role("button",name="获取授权链接",exact=True).click()
            page.get_by_role("alert").filter(has_text="Qoder CN 暂不可用").wait_for()
            login_fixture.update(available=True,detail="CLI 已安装",auth_ui=False,model_discovery=True)
            page.get_by_role("button",name="刷新状态").click()
            page.get_by_text("服务器执行服务版本过旧，不支持网页授权。",exact=True).wait_for()
            page.get_by_role("button",name="获取授权链接",exact=True).click()
            page.get_by_role("alert").filter(has_text="尚不支持网页授权").wait_for()
            login_fixture.update(auth_ui=True)
            page.get_by_role("button",name="刷新状态").click()
            page.get_by_text("服务器执行服务版本过旧，不支持网页授权。",exact=True).wait_for(state="detached")
            # Observe the real browser, not a patched window.open counter. Patching
            # window.open would itself prevent detecting an actual popup.
            authorization_pages=[]
            context.on("page", lambda opened: authorization_pages.append(opened))
            authorization_origin=page.url
            existing_pages=len(context.pages)
            def start_login(route):
                login_fixture["login"]={"state":"waiting","url":"https://qoder.com.cn/auth/login?state=preview","detail":"请在浏览器完成官方授权"}
                route.fulfill(status=200,content_type="application/json",body=json.dumps(login_fixture["login"],ensure_ascii=False))
            context.route("**/api/qoder/login/start",start_login)
            page.get_by_role("button",name="获取授权链接",exact=True).click()
            page.locator(".auth-inline-row").wait_for()
            expect(page.locator(".auth-inline-row input")).to_have_count(1)
            expect(page.locator(".auth-inline-row textarea")).to_have_count(0)
            expect(page.get_by_label("授权链接",exact=True)).to_have_value("https://qoder.com.cn/auth/login?state=preview")
            # The URL must be visible, authorization must remain on the same page,
            # and no new browser tab/window may be opened by requesting the link.
            expect(page.get_by_role("button",name="复制授权链接",exact=True)).to_be_enabled()
            expect(page.get_by_role("button",name="刷新状态",exact=True)).to_be_enabled()
            expect(page.get_by_role("button",name="取消本次授权",exact=True)).to_be_enabled()
            assert page.url==authorization_origin, f"Unexpected navigation: {page.url}"
            assert len(context.pages)==existing_pages and not authorization_pages, "Unexpected automatic authorization popup"
            expect(page.get_by_text("等待授权",exact=True)).to_be_visible()
            capture(page,path=str(OUT/"31-qoder-auth-mobile.png"),full_page=False)
            # Complete the simulated official login: the current account's actual
            # catalog must be fetched automatically, not the compatibility defaults.
            model_requests=[]
            live_catalog={"models":[{"id":"Auto","label":"Auto","efforts":["default"]},{"id":"preview-new-model","label":"Preview New Model","efforts":["default"]}],"source":"cli","updated_at":1}
            def latest_models(route):
                model_requests.append(route.request.method)
                route.fulfill(status=200,content_type="application/json",body=json.dumps(live_catalog))
            context.route("**/api/qoder/models/refresh",latest_models)
            login_fixture["login"]={"state":"finished","url":"","detail":"CLI 登录流程已结束"}
            page.get_by_text("最新模型清单已更新（2 个）",exact=True).wait_for(timeout=15000)
            assert model_requests==["POST"]
            expect(page.get_by_text("可用模型：2",exact=True)).to_be_visible()
            assert page.url==authorization_origin
            assert len(context.pages)==existing_pages and not authorization_pages, "Unexpected popup during authorization polling"
            page.get_by_role("button",name="模型配置",exact=True).click()
            page.get_by_role("button",name="修改",exact=True).click()
            page.get_by_label("AI 助手模型",exact=True).locator("option[value='preview-new-model']").wait_for(state="attached")
            assert page.get_by_label("AI 助手模型",exact=True).evaluate("(el) => Array.from(el.options).some(o => o.value === 'preview-new-model')")
            assert page.get_by_label("视频制作与微调模型",exact=True).evaluate("(el) => Array.from(el.options).some(o => o.value === 'preview-new-model')")
    except Exception:
        try:
            page.screenshot(path=str(OUT/("failure-"+GROUP+".png")),full_page=False,timeout=5000)
        except Exception as screenshot_error:
            print("Failure screenshot unavailable:",screenshot_error)
        raise
    finally:
        browser.close()
(OUT/"README.txt").write_text("Compiled React UI, isolated synthetic fixtures. Not production data or a production deployment screenshot.\n",encoding="utf-8")
