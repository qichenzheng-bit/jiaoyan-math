"""Actual compiled React screenshots with isolated, synthetic API responses. No production credentials."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
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
 {"id":"msg-ai","role":"assistant","content":"可以整理为题目草稿，请确认。","state":"done","detail":"","model":"Auto","attachments":[],"resource_refs":[],"intake_intent":"question"}]}
review_job={"id":"review-demo","title":"补充示例","state":"review","detail":"待人工核对","revision":1,"document_id":None,"input_text":"求导数","items":[{"uid":"review-item","kind":"question","title":"导数计算","content":r"求 $x^2$ 的导数。","answer":"","solution":"","analysis":"","proof":"","chapter":"","question_type":"","unit_type":""}]}
review_suggestion={"id":"supplement-demo","job_id":"review-demo","item_uid":"review-item","base_revision":1,"fields":["answer","solution"],"state":"review","detail":"AI生成待确认","proposal":{"answer":"$2x$","solution":r"利用幂函数求导公式，$(x^2)'=2x$。"},"accepted":[],"model":"Auto"}
ai_doc={**doc,"id":"ai-demo","blocks":[{"uid":"ai-q1","kind":"question","title":"导数计算","content":r"求 $x^2$ 的导数。","answer":"$2x$","solution":"","analysis":"","proof":"","chapter":"","question_type":"解答题","unit_type":"","resource_id":None,"file_id":None,"width":100}]}
ai_edit={"id":"edit-demo","document_id":"ai-demo","base_revision":1,"fields":["solution"],"instruction":"逐步推导","model":"Auto","state":"review","detail":"待确认","change_count":1,"changes":[{"uid":"ai-q1","field":"solution","before":"","after":r"由幂函数求导公式，$(x^2)'=2x$。"}],"accepted":[]}
registration_preview={"revision":1,"items":[{"uid":"ai-q1","candidates":[],"knowledge":[{"id":"p4","name":"导数","code":"KP4","chapter":"微积分","matched":"导数"}],"chapter_suggestion":"微积分","peer_ids":[],"missing":["solution"]}],"similar_scan_limit":300}
def answer(route):
    from urllib.parse import urlsplit,parse_qs
    u=urlsplit(route.request.url);p=u.path.removeprefix("/api");q=parse_qs(u.query)
    result={
      "/auth/me":{"username":"预览管理员"},"/ready":{"status":"ok"},"/settings":{"display_name":"微光数学","theme":"light"},"/resources/subjects":subjects,
      "/knowledge/points":{"items":points,"total":len(points)},"/knowledge/relations":{"items":edges,"truncated":False},
      "/documents/demo":doc,"/documents/source-export/source-preview":{**doc,"kind":"paper","source_export":True,"has_source_content":True,"batch_count":1},"/documents/demo/origin":{"job_id":"review-demo","input_text":r"原始资料 $x^2$","provenance":{"kind":"manual"},"supplements":[]},"/resources/source-preview":source,"/documents":{"items":[{k:v for k,v in doc.items() if k!="blocks"}],"total":1},
      "/intelligence/jobs":[],"/intelligence/import/capabilities":{"text":True,"docx":True,"pdf_text":True,"image_ocr":False,"pdf_ocr":False},"/chat/sessions/chat-demo":demo_chat,"/intelligence/chat-source/msg-user":{"message_id":"msg-user","session_id":"chat-demo","role":"user","text":demo_chat["messages"][0]["content"],"title":demo_chat["title"],"has_attachments":False},"/chat/sessions":[{k:v for k,v in demo_chat.items() if k!="messages"}],"/qoder/status":{"available":True,"chat_available":True,"worker_version":4},"/qoder/models":{"models":[{"id":"Auto","label":"Auto"}]},"/qoder/preferences":{"model":"Auto"},
      "/settings/status":{"version":"preview","release":"synthetic-preview","disk":None},"/settings/audit":[],
      "/studio/presets":{"bilibili":[1920,1200,5,5,4,4],"douyin":[1080,1920,13,21,4,16.5],"xiaohongshu":[1242,1660,6,12,5,12],"wechat_top":[900,383,6,30,28,28],"wechat_sub":[500,500,8,8,8,8]},
      "/studio":{"items":[],"total":0},"/video/status":{"available":False,"detail":"隔离预览：未配置视频引擎","source_revision":"preview"},"/video/projects":[],"/tasks":[],"/files/stats":{"count":0,"bytes":0,"max_file_bytes":20971520}
    }.get(p)
    if p=="/documents/ai-demo":
        result=ai_doc
        if route.request.method=="PUT":
            result={**json.loads(route.request.post_data),"revision":2}
    if p=="/documents/manual-matches" and route.request.method=="POST":
        body=json.loads(route.request.post_data)
        result={"items":[{"resource":items[1],"match_kind":"similar","similarity":.87}] if "测试查重" in body["content"] else [],"scanned":len(items),"scope":"full_active_question_bank"}
    if p=="/documents/ai-demo/manual-save" and route.request.method=="POST":
        body=json.loads(route.request.post_data)
        result={**body,"revision":body["revision"]+1,"blocks":[{**b,"kind":"reference","resource_id":"saved-"+b["uid"],"snapshot":{**b,"code":"QNEW","kind":b["kind"],"id":"saved-"+b["uid"]}} if b["kind"] in ("question","knowledge") else b for b in body["blocks"]]}
    if p=="/documents/ai-demo/ai-edits":result=[ai_edit]
    if p.endswith("/registration-history"):result=[]
    if p=="/documents/ai-demo/registration-preview":result=registration_preview
    if p=="/documents/ai-demo/ai-edits/edit-demo":result=ai_edit
    if p=="/intelligence/jobs/review-demo":result=review_job
    if p=="/intelligence/jobs/review-demo/supplements":result=[review_suggestion]
    if p=="/files" and route.request.method=="POST":
        result={"id":"file-demo","name":q.get("name",["demo.tex"])[0],"media_type":"text/plain","previewable":False}
    if p=="/intelligence/import" and route.request.method=="POST":
        result={"import_id":"import-demo","file_id":"file-demo","file_name":"demo.tex","text":r"求 $\frac{1}{x}$ 的导数。","method":"text","start":1,"end":1,"total_units":None,"warnings":[]}
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
    for path,name in [("/","00-home"),("/overview","29-overview"),("/library","11-library"),("/create","12-create"),("/videos","13-video"),("/products","14-products"),("/operations","15-operations"),("/intake","01-intake"),("/intake?mode=document","16-intake-document"),("/intake-single?kind=knowledge","17-intake-knowledge"),("/intelligence","18-intelligence"),("/intelligence?job=review-demo","22-intake-supplement"),("/resources","02-bank"),("/graph","03-graph"),("/intake?doc=demo","04-word"),("/intake?doc=ai-demo","25-word-ai"),("/chat","05-chat"),("/chat?session=chat-demo","19-intake-intent"),("/covers","06-cover"),("/checkin","07-checkin"),("/settings","08-settings")]:
        page.goto("http://127.0.0.1:4173"+path,wait_until="networkidle")
        page.wait_for_selector(".legacy-shell",timeout=10000)
        assert page.locator(".main-section-links").is_visible() or page.locator(".nav").count()==1
        assert page.locator(".mobile-tabs,.clean-context-menu,.clean-local-nav").count()==0
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(300)
        if name=="01-intake":
            assert page.locator(".intake-entry").count()==2
            assert page.locator(".intake-entry[href='/work']").is_visible()
            assert page.locator(".intake-entry[href='/intake?mode=document']").is_visible()
            assert page.locator(".intake-hub a[href^='/intake-single']").count()==0
            assert page.locator(".intake-flow-steps > div").count()==4
        if name=="16-intake-document":
            page.get_by_role("button",name="复用已有来源").click()
            page.get_by_label("选择来源资料",exact=True).first.click()
            page.locator(".math-choice-options").get_by_role("button").filter(has_text="SDEMO0001").click()
            assert page.locator(".source-selected").is_visible()
            assert page.get_by_label("录入批次名称").input_value()==source["title"]
            page.screenshot(path=str(OUT/"21-source-reuse.png"),full_page=False)
        if name=="17-intake-knowledge":
            assert page.get_by_role("button",name="知识单元",exact=True).get_attribute("aria-pressed")=="true"
        if name=="05-chat":
            assert page.locator(".intake-chat-prompts").count()==0
            assert page.locator(".chat-home-recent").is_visible()
            page.get_by_label("输入消息").fill(r"录入题目：求 $\lim_{x\to0}\frac{\sin x}{x}$。")
            page.get_by_role("button",name="添加与工具").click()
            page.get_by_role("button",name="转录入",exact=True).click()
            page.wait_for_url("**/work")
            assert page.get_by_label("输入录入资料",exact=True).input_value().startswith("录入题目")
            assert page.get_by_text("已带入聊天正文").is_visible()
            page.goto("http://127.0.0.1:4173/chat",wait_until="networkidle")
        if name=="22-intake-supplement":
            page.locator(".supplement-proposal .katex").first.wait_for()
            assert page.get_by_role("button",name="确认生成录入文档").is_disabled()
            assert page.get_by_role("button",name="确认选中补充内容").is_enabled()
            assert page.locator(".supplement-proposal").get_by_text("待审核 · AI生成内容").is_visible()
        if name=="18-intelligence":
            page.get_by_label("选择录入文件").set_input_files({"name":"demo.tex","mimeType":"text/plain","buffer":b"test formula"})
            page.get_by_role("button",name="发送资料").click()
            page.locator(".work-review-preview .katex").first.wait_for()
            assert page.get_by_label("输入录入资料",exact=True).input_value()==r"求 $\frac{1}{x}$ 的导数。"
            assert page.locator(".intelligence-stages").count()==0
            assert page.locator(".material-import").count()==0
        if name=="19-intake-intent":
            page.locator(".chat-intake-suggestion").wait_for()
            assert page.locator(".chat-message.user .chat-message-body").evaluate("(el)=>getComputedStyle(el).width !== getComputedStyle(el.parentElement).width")
            assert page.locator(".chat-message-actions").get_by_role("button",name="复制",exact=True).first.is_visible()
            assert page.locator(".clean-chat header,.clean-chat .chat-top").count()==0
            page.get_by_role("button",name="更多选项",exact=True).click()
            page.locator("#chat-session-actions").get_by_role("button",name="管理",exact=True).wait_for()
            page.get_by_role("button",name="更多选项",exact=True).click()
            page.screenshot(path=str(OUT/(name+".png")),full_page=False)
            page.get_by_role("button",name="使用本次用户原文").click()
            page.wait_for_url("**/work?from=msg-user&intent=question")
            page.get_by_label("输入录入资料",exact=True).wait_for()
            page.get_by_text("已带入聊天正文").wait_for()
            assert page.get_by_label("输入录入资料",exact=True).input_value()==demo_chat["messages"][0]["content"]
            page.get_by_role("button",name="添加录入资料").click()
            assert page.get_by_label("录入目标").input_value()=="question"
            page.get_by_role("button",name="添加录入资料").click()
            page.screenshot(path=str(OUT/"20-intake-linked.png"),full_page=False)
            continue
        if name=="00-home":
            assert page.get_by_label("输入消息").is_visible()
            assert page.locator(".clean-chat.chat-main-area").count()==1
            assert page.locator(".clean-chat .chat-main-area").count()==0
            assert page.locator(".workspace > header").count()==1
            assert page.locator(".clean-chat header,.clean-chat .chat-top").count()==0
            assert page.locator(".clean-chat > .chat-composer > textarea").count()==1
            assert page.get_by_label("输入消息").evaluate("(el) => getComputedStyle(el).borderTopWidth === '0px' && getComputedStyle(el).boxShadow === 'none'")
            assert page.get_by_text("今天想做什么？",exact=True).count()==0
            assert page.locator(".chat-home-recent").is_visible()
            assert page.locator(".mode-switch").get_by_role("link",name="聊天").get_attribute("aria-current")=="page"
            page.get_by_role("button",name="更多选项",exact=True).click()
            assert page.locator("#mode-more-panel").get_by_role("link",name="AI 登录与模型").get_attribute("href")=="/qoder"
            page.get_by_role("button",name="更多选项",exact=True).click()
            page.locator(".mode-switch").get_by_role("link",name="工作").click()
            page.get_by_role("region",name="资料录入").wait_for()
            assert page.get_by_label("输入录入资料").is_visible()
            assert page.get_by_role("button",name="添加录入资料").is_visible()
            page.get_by_role("button",name="添加录入资料").click()
            page.get_by_role("button",name="上传图片、PDF 或 Word").wait_for()
            page.get_by_role("button",name="添加录入资料").click()
            page.get_by_label("选择录入文件").set_input_files({"name":"demo.tex","mimeType":"text/plain","buffer":b"test formula"})
            page.get_by_role("button",name="发送资料").click()
            page.locator(".work-review-preview .katex").first.wait_for()
            page.once("dialog",lambda dialog:dialog.accept())
            page.get_by_role("button",name="移除资料").click()
            assert page.locator(".mode-switch").get_by_role("link",name="工作").get_attribute("aria-current")=="page"
            page.get_by_role("button",name="更多选项",exact=True).click()
            assert page.locator("#mode-more-panel").get_by_role("link",name="AI 登录与模型").is_visible()
            page.get_by_role("button",name="更多选项",exact=True).click()
            assert page.locator(".workflow-board").count()==0
            page.locator(".mode-switch").get_by_role("link",name="聊天").click()
            page.locator(".chat-home-recent").wait_for()
            assert page.locator(".chat-history").count()==0
            assert page.locator(".workflow-step").count()==0
            assert page.locator(".clean-recent").get_by_text(demo_chat["title"],exact=True).is_visible()
            page.locator(".clean-recent").get_by_text(demo_chat["title"],exact=True).click()
            page.locator(".chat-intake-suggestion").wait_for()
            page.locator("#workspace-navigation").get_by_role("link",name="新建对话").click()
            page.locator(".chat-home-recent").wait_for()
            page.locator(".clean-recent").first.get_by_role("button",name="全部",exact=True).click()
            page.locator("#workspace-navigation").get_by_label("搜索会话").wait_for()
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
            assert page.locator(".project-hub .project-link").count()==4
            page.locator("#workspace-navigation").get_by_role("link",name="教学教研",exact=True).click()
            page.wait_for_url("**/project/teaching")
            page.locator(".project-hub").get_by_role("heading",name="教学教研",exact=True).wait_for()
            assert page.locator(".project-hub .project-link").count()==4
            for label in ("题库","知识库","知识图谱","来源库"):
                assert page.locator(".project-hub").get_by_role("link",name=label,exact=True).is_visible()
            assert page.locator(".project-hub").get_by_role("link",name="视频制作",exact=True).count()==0
            page.locator("#workspace-navigation").get_by_role("link",name="资料录入",exact=True).click()
            page.wait_for_url("**/project/intake")
            page.locator(".project-hub").get_by_role("heading",name="资料录入",exact=True).wait_for()
            intake_section=page.locator(".project-hub")
            assert intake_section.locator(".project-link").count()==2
            assert intake_section.get_by_role("link",name="AI 录入",exact=True).get_attribute("href")=="/work"
            assert intake_section.get_by_role("link",name="整套资料录入",exact=True).get_attribute("href")=="/intake?mode=document"
            page.locator("#workspace-navigation").get_by_role("link",name="教学制作",exact=True).click()
            page.wait_for_url("**/project/creation")
            page.locator(".project-hub").get_by_role("heading",name="教学制作",exact=True).wait_for()
            for label in ("视频制作","组卷","组讲义","组教材"):
                assert page.locator(".project-hub").get_by_role("link",name=label,exact=True).is_visible()
            assert page.locator("#workspace-navigation .clean-nav-children").count()==0
            page.locator("#workspace-navigation").get_by_role("link",name="内容发布",exact=True).click()
            page.wait_for_url("**/project/publishing")
            page.locator(".project-hub").get_by_role("heading",name="内容发布",exact=True).wait_for()
            assert page.locator(".project-hub .project-link").count()==1
            assert page.locator(".project-hub").get_by_role("link",name="封面设计",exact=True).is_visible()
            page.locator("#workspace-navigation").get_by_role("link",name="商品售卖",exact=True).click()
            page.wait_for_url("**/project/sales")
            page.locator(".project-hub").get_by_role("heading",name="商品售卖",exact=True).wait_for()
            page.locator(".project-hub").get_by_role("link",name="商品售卖",exact=True).click()
            page.get_by_text("商品上架",exact=True).wait_for()
            assert page.locator(".module-hub").get_by_role("link",name="教学作品",exact=True).count()==0
            page.goto("http://127.0.0.1:4173/create",wait_until="networkidle")
            assert page.locator(".clean-context-menu").count()==0
        if name=="13-video":
            assert page.locator(".video-stage-track > div").count()==5
        if name=="02-bank":
            page.get_by_role("button",name="高级筛选").click()
            assert page.get_by_label("章节",exact=True).is_visible()
            page.get_by_role("button",name="收起筛选").click()
            page.locator(".bank-detail .katex").first.wait_for()
            assert page.locator(".bank-list .katex").count()>0
        if name=="25-word-ai":
            page.get_by_role("button",name="批量审核入库").click()
            page.get_by_role("button",name="检查重复与知识点").click()
            page.locator(".doc-review-item").wait_for()
            page.get_by_role("button",name="采用建议章节",exact=False).click()
            page.get_by_label("导数",exact=False).last.check()
            assert page.get_by_role("button",name="确认批量入库（1 条）").is_enabled()
            page.screenshot(path=str(OUT/"26-registration-review.png"),full_page=False)
            page.get_by_role("button",name="AI协作",exact=True).click()
            page.locator(".doc-ai-after .katex").first.wait_for()
            assert page.get_by_role("button",name="采纳选中修改").is_enabled()
            assert page.locator(".doc-ai-change").count()==1
            assert page.locator(".doc-sheet").get_by_text("由幂函数求导公式",exact=False).count()==0
        if name=="04-word":
            page.locator(".doc-sheet .katex").first.wait_for()
            assert page.locator(".doc-outline-item").count()==4
            page.get_by_role("button",name="待入库",exact=True).click()
            assert page.locator(".doc-outline-item").count()==0
            page.locator(".doc-outline").get_by_role("button",name="全部",exact=True).click()
            page.locator(".doc-outline-item").first.click()
            assert page.locator(".doc-block.selected").count()==1
            page.get_by_role("button",name="原文",exact=True).click()
            page.locator(".doc-origin-text .katex").first.wait_for()
            page.screenshot(path=str(OUT/"23-word-origin.png"),full_page=False)
            page.get_by_role("button",name="编辑",exact=True).click()
            page.set_viewport_size({"width":393,"height":873})
            page.locator(".mobile-doc-card").wait_for()
            page.locator(".manual-render .katex").first.wait_for()
            assert page.locator(".doc-canvas").count()==0
            assert page.get_by_role("button",name="AI 修改",exact=True).count()==0
            assert page.get_by_role("button",name="原文对照",exact=True).count()==0
            assert page.get_by_role("link",name="导出 PDF",exact=True).count()==0
            page.get_by_role("button",name="下一条",exact=True).click()
            assert page.locator(".mobile-doc-card h2").inner_text()=="第 2 题"
            page.get_by_role("button",name="全部题目",exact=True).click()
            assert page.locator(".manual-list-row").count()==4
            page.get_by_role("button",name="整套预览",exact=True).click()
            assert page.locator(".manual-intake-preview .katex").count()>0
            page.get_by_role("button",name="编辑第 1 个条目",exact=True).click()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(OUT/"27-mobile-card.png"),full_page=False)
            page.get_by_role("button",name="切换 Word 版").click()
            page.get_by_role("navigation",name="文档面板").get_by_role("button",name="页面").click()
            assert page.locator(".doc-canvas").is_visible()
            assert not page.locator(".doc-side").is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(OUT/"24-word-mobile.png"),full_page=False)
            page.set_viewport_size({"width":1600,"height":900})
        if name=="06-cover":
            page.get_by_label("主标题").fill(r"求极限 $\lim_{x\to0}\frac{\sin x}{x}$")
            page.locator(".math-cover-art .katex").first.wait_for()
        page.screenshot(path=str(OUT/(name+".png")),full_page=False)
    # Phone-first intake: edit formulas in place, navigate without committing, save all at once.
    page.set_viewport_size({"width":393,"height":873})
    page.goto("http://127.0.0.1:4173/intake?doc=ai-demo",wait_until="networkidle")
    page.locator(".mobile-doc-card").wait_for()
    page.get_by_label("题目",exact=True).fill(r"求 $\frac{1}{x}$ 的导数。")
    page.get_by_label("难度",exact=True).select_option("中等")
    page.get_by_label("题目",exact=True).locator(".inline-math-token .katex").wait_for()
    page.get_by_label("题目",exact=True).locator(".inline-math-token").click()
    page.get_by_label("编辑 LaTeX 公式",exact=True).fill(r"$\frac{1}{x^2}$")
    page.get_by_label("难度",exact=True).click()
    page.get_by_label("题目",exact=True).locator(".inline-math-token .katex").wait_for()
    assert page.get_by_label("编辑 LaTeX 公式",exact=True).count()==0
    assert page.get_by_role("button",name="保存整套资料",exact=True).is_enabled()
    assert page.get_by_label("条目标题",exact=True).count()==0
    page.get_by_role("button",name="切换 Word 版").click()
    assert page.locator(".doc-sheet").get_by_text("的导数",exact=False).count()>0
    assert page.locator(".doc-sheet .katex").count()>0
    page.get_by_role("button",name="切换卡片版").click()
    assert page.get_by_label("题目",exact=True).locator(".inline-math-token").get_attribute("data-math-source")==r"$\frac{1}{x^2}$"
    assert page.get_by_role("button",name="＋ 选择题",exact=True).count()==0
    page.get_by_role("button",name="下一条 · 新增",exact=True).click()
    assert page.get_by_label("题目",exact=True).count()==0
    page.get_by_role("button",name="＋ 选择题",exact=True).click()
    page.get_by_label("题目",exact=True).fill("选择正确答案")
    page.get_by_label("A 选项",exact=True).fill("$1$")
    page.get_by_label("B 选项",exact=True).fill("$2$")
    page.locator(".manual-answer-choices").get_by_role("button",name="A",exact=True).click()
    assert page.get_by_text("正确选项 · 单选题",exact=True).is_visible()
    page.locator(".manual-answer-choices").get_by_role("button",name="B",exact=True).click()
    assert page.get_by_text("正确选项 · 多选题",exact=True).is_visible()
    page.get_by_role("button",name="下一条 · 新增",exact=True).click()
    page.get_by_role("button",name="＋ 填空题",exact=True).click()
    page.get_by_label("题目",exact=True).fill("计算")
    page.get_by_role("button",name="＋ 插入填空空位",exact=True).click()
    assert "underline" in page.get_by_label("题目",exact=True).locator(".inline-math-token").get_attribute("data-math-source")
    page.get_by_role("button",name="下一条 · 新增",exact=True).click()
    page.get_by_role("button",name="＋ 解答题",exact=True).click()
    page.get_by_label("题目",exact=True).fill("已知函数")
    assert page.get_by_label("第 1 小问题目",exact=True).count()==0
    page.get_by_role("button",name="＋ 添加小问（可选）",exact=True).click()
    page.get_by_label("第 1 小问题目",exact=True).fill("求导数")
    page.get_by_label("第 1 小问答案",exact=True).fill("$2x$")
    page.get_by_label("第 1 小问解析",exact=True).fill("利用导数公式")
    page.get_by_label("知识标签",exact=True).fill("导数")
    page.get_by_label("知识标签",exact=True).press("Enter")
    assert page.get_by_role("button",name="移除知识标签 导数",exact=True).is_visible()
    page.get_by_role("button",name="下一条 · 新增",exact=True).click()
    page.get_by_role("button",name="＋ 解答题",exact=True).click()
    page.get_by_label("题目",exact=True).fill("测试查重")
    page.get_by_role("button",name="使用原题 · 编号不变",exact=True).wait_for()
    page.once("dialog",lambda dialog:dialog.accept())
    page.get_by_role("button",name="使用原题 · 编号不变",exact=True).click()
    assert page.get_by_label("题目",exact=True).get_attribute("contenteditable")=="false"
    assert page.get_by_text("已选择原题 QDEMO0002",exact=False).is_visible()
    page.get_by_role("button",name="编辑相关信息 · 另存为新题",exact=True).click()
    assert page.get_by_label("题目",exact=True).get_attribute("contenteditable")=="true"
    page.get_by_label("题目",exact=True).fill("修改为新题")
    page.get_by_role("button",name="整套预览",exact=True).click()
    assert page.locator(".manual-intake-preview .print-question-number").count()==5
    assert page.locator(".manual-intake-preview .katex").count()>0
    assert page.get_by_role("button",name="打印 / 保存为 PDF",exact=True).count()==0
    assert page.get_by_text("已保存并直接入库",exact=True).count()==0
    with page.expect_request(lambda req: req.url.endswith("/documents/ai-demo/manual-save") and req.method=="POST") as request_info:
        page.get_by_role("button",name="保存整套资料",exact=True).click()
    submitted=request_info.value.post_data_json
    assert len(submitted["blocks"])==5
    assert submitted["blocks"][0]["difficulty"]=="中等"
    assert submitted["blocks"][1]["question_type"]=="多选题"
    page.get_by_text("已保存并直接入库",exact=True).wait_for()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(OUT/"28-mobile-review.png"),full_page=False)
    page.set_viewport_size({"width":1600,"height":900})
    # Theme and mobile smoke checks use the same compiled application.
    page.goto("http://127.0.0.1:4173/",wait_until="networkidle")
    assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim().toLowerCase()") == "#ffffff"
    page.evaluate("document.documentElement.dataset.theme='dark'")
    page.screenshot(path=str(OUT/"09-home-dark.png"),full_page=False)
    page.evaluate("document.documentElement.dataset.theme='light'")
    page.set_viewport_size({"width":393,"height":873})
    page.screenshot(path=str(OUT/"10-home-mobile.png"),full_page=False)
    assert page.locator(".mobile-tabs").count()==0
    assert page.get_by_label("输入消息").is_visible()
    assert page.locator(".clean-chat > .compact-composer").is_visible()
    assert page.locator(".mode-switch").is_visible()
    page.get_by_role("button",name="添加与工具").click()
    assert page.get_by_role("group",name="聊天工具").is_visible()
    page.get_by_role("button",name="添加与工具").click()
    assert page.locator(".workspace > header").count()==1
    assert page.locator(".clean-chat header,.clean-chat .chat-top").count()==0
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
    drawer.get_by_role("link",name="教学教研",exact=True).click()
    page.wait_for_url("**/project/teaching")
    page.locator(".project-hub").get_by_role("heading",name="教学教研",exact=True).wait_for()
    expect(drawer).to_have_count(0)
    assert page.locator(".project-hub").get_by_role("link",name="来源库",exact=True).is_visible()
    menu.click()
    expect(drawer).to_be_visible()
    drawer.get_by_role("link",name="资料录入",exact=True).click()
    page.wait_for_url("**/project/intake")
    page.locator(".project-hub").get_by_role("heading",name="资料录入",exact=True).wait_for()
    expect(drawer).to_have_count(0)
    page.locator(".project-hub").get_by_role("link",name="整套资料录入",exact=True).click()
    page.wait_for_url("**/intake?mode=document")
    page.locator(".legacy-intake").wait_for()
    assert not page.locator(".nav.open").count()
    page.goto("http://127.0.0.1:4173/sources",wait_until="networkidle")
    page.locator(".bank-row").first.click()
    page.get_by_role("link",name="导出 PDF",exact=True).click()
    page.wait_for_url("**/source-print/source-preview")
    page.locator(".print-document .katex").first.wait_for()
    assert page.locator(".print-question-number").count()==4
    assert page.get_by_role("button",name="打印 / 保存为 PDF",exact=True).is_enabled()
    page.get_by_label("仅题目").check()
    assert page.locator(".print-document").get_by_text("答案：",exact=False).count()==0
    page.goto("http://127.0.0.1:4173/resources",wait_until="networkidle")
    page.locator(".bank-row").first.wait_for()
    assert page.locator(".bank-detail").is_hidden()
    page.locator(".bank-row").first.click()
    page.locator(".bank-detail .katex").first.wait_for()
    assert page.locator(".bank-list").is_hidden()
    page.screenshot(path=str(OUT/"30-resource-mobile.png"),full_page=False)
    page.get_by_role("button",name="返回资源列表",exact=False).click()
    assert page.locator(".bank-list").is_visible()
    page.goto("http://127.0.0.1:4173/works",wait_until="networkidle")
    assert page.locator(".studio-library").is_visible()
    page.get_by_role("button",name="新建",exact=True).click()
    assert page.locator(".clean-studio .resource-form").is_visible()
    assert page.locator(".studio-library").is_hidden()
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
    assert page.locator(".auth-inline-row input").count()==1
    assert page.locator(".auth-inline-row textarea").count()==0
    assert page.get_by_label("授权链接",exact=True).input_value()=="https://qoder.com.cn/auth/login?state=preview"
    # The URL must be visible, authorization must remain on the same page,
    # and no new browser tab/window may be opened by requesting the link.
    expect(page.get_by_role("button",name="复制授权链接",exact=True)).to_be_enabled()
    expect(page.get_by_role("button",name="刷新状态",exact=True)).to_be_enabled()
    expect(page.get_by_role("button",name="取消本次授权",exact=True)).to_be_enabled()
    assert page.url==authorization_origin, f"Unexpected navigation: {page.url}"
    assert len(context.pages)==existing_pages and not authorization_pages, "Unexpected automatic authorization popup"
    assert page.get_by_text("等待授权",exact=True).is_visible()
    page.screenshot(path=str(OUT/"31-qoder-auth-mobile.png"),full_page=False)
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
    browser.close()
(OUT/"README.txt").write_text("Compiled React UI, isolated synthetic fixtures. Not production data or a production deployment screenshot.\n",encoding="utf-8")
