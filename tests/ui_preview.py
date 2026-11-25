"""Actual compiled React screenshots with isolated, synthetic API responses. No production credentials."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
OUT=Path("ui-screenshots");OUT.mkdir(exist_ok=True)
subjects=["高等数学","线性代数","概率论与数理统计","数学分析","高等代数"]
source={"id":"source-preview","code":"SDEMO0001","kind":"source","title":"考研数学（一）示例试卷","subject":"高等数学","content":"示例资料","source_type":"exam","tags":[],"archived":False,"revision":1}
items=[dict(id=f"q{i}",code=f"QDEMO{i:04}",kind="question",title=t,subject="高等数学",chapter="一元函数微分学",question_type="解答题",content=c,answer=a,solution=s,analysis="",proof="",unit_type="",source_type="",source_id=source["id"],tags=tags,archived=False,revision=1,sources_revision=1) for i,(t,c,a,s,tags) in enumerate([
("重要极限",r"求极限 $\lim_{x\to0}\frac{\sin x}{x}$。","$1$",r"根据重要极限，$\lim_{x\to0}\frac{\sin x}{x}=1$。",["重要极限","极限运算"]),
("导数计算",r"设 $f(x)=x^2e^x$，求 $f'(x)$。",r"$e^x(x^2+2x)$","使用乘积求导法则。",["导数","乘积法则"]),
("定积分",r"计算 $\int_0^1 x^2\,dx$。",r"$\frac13$","使用牛顿—莱布尼茨公式。",["定积分"]),
("矩阵计算",r"计算 $\det\begin{pmatrix}1&2\\3&4\end{pmatrix}$。","$-2$","使用二阶行列式公式。",["行列式"])],1)]
doc={"id":"demo","title":"考研数学（一）示例试卷","kind":"intake","subject":"高等数学","source_id":source["id"],"revision":1,"archived":False,"blocks":[{"uid":q["id"],"kind":"reference","title":"","content":"","answer":"","solution":"","analysis":"","proof":"","chapter":"","question_type":"","unit_type":"","resource_id":q["id"],"file_id":None,"width":100,"snapshot":q} for q in items]}
points=[dict(id=f"p{i}",code=f"KP{i}",name=n,subject="高等数学",chapter="微积分",description="示例知识点",aliases=[],status="active",revision=1) for i,n in enumerate(["微积分","一元函数微分学","一元函数积分学","重要极限","导数","微分中值定理","定积分","换元积分法","分部积分法"])]
edges=[dict(source_id=f"p{a}",target_id=f"p{b}",relation_type="contains") for a,b in [(0,1),(0,2),(1,3),(1,4),(1,5),(2,6),(2,7),(2,8)]]
def answer(route):
    from urllib.parse import urlsplit,parse_qs
    u=urlsplit(route.request.url);p=u.path.removeprefix("/api");q=parse_qs(u.query)
    result={
      "/auth/me":{"username":"预览管理员"},"/ready":{"status":"ok"},"/settings":{"display_name":"微光数学","theme":"light"},"/resources/subjects":subjects,
      "/knowledge/points":{"items":points,"total":len(points)},"/knowledge/relations":{"items":edges,"truncated":False},
      "/documents/demo":doc,"/documents":{"items":[{k:v for k,v in doc.items() if k!="blocks"}],"total":1},
      "/chat/sessions":[],"/qoder/status":{"available":True,"chat_available":True,"worker_version":4},"/qoder/models":{"models":[{"id":"Auto","label":"Auto"}]},"/qoder/preferences":{"model":"Auto"},
      "/settings/status":{"version":"preview","release":"synthetic-preview","disk":None},"/settings/audit":[],
      "/studio/presets":{"bilibili":[1920,1200,5,5,4,4],"douyin":[1080,1920,13,21,4,16.5],"xiaohongshu":[1242,1660,6,12,5,12],"wechat_top":[900,383,6,30,28,28],"wechat_sub":[500,500,8,8,8,8]},
      "/studio":{"items":[],"total":0},"/tasks":[],"/files/stats":{"count":0,"bytes":0,"max_file_bytes":20971520}
    }.get(p)
    if p=="/resources":
        rows=[source] if q.get("kind")==["source"] else items
        result={"items":rows,"total":len(rows)}
    if p.startswith("/knowledge/points/") and p.endswith("/resources"):result=[]
    if result is None:result={}
    route.fulfill(status=200,content_type="application/json",body=json.dumps(result,ensure_ascii=False))
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(viewport={"width":1600,"height":900},device_scale_factor=1)
    context.route("**/api/**",answer)
    page=context.new_page()
    for path,name in [("/intake","01-intake"),("/resources","02-bank"),("/graph","03-graph"),("/intake?doc=demo","04-word"),("/chat","05-chat"),("/covers","06-cover"),("/checkin","07-checkin"),("/settings","08-settings")]:
        page.goto("http://127.0.0.1:4173"+path,wait_until="networkidle")
        page.wait_for_selector(".legacy-shell",timeout=10000)
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT/(name+".png")),full_page=False)
    browser.close()
(OUT/"README.txt").write_text("Compiled React UI, isolated synthetic fixtures. Not production data or a production deployment screenshot.\n",encoding="utf-8")
