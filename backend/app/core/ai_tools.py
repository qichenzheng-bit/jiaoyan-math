"""Explicit, validated AI business-tool registry. No arbitrary route, SQL or shell access."""
import inspect
import json
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.fields import FieldInfo

from app.api import resources, knowledge, source_catalog, documents, settings, video, workspaces, bank_work, studio, qiandao, qoder, teaching_works
from app.models import TeachingResource, StoredFile, ChatSession, ChatMessage, WorkSession
from app.services import material_import, material_vision, storage
from sqlalchemy import select, func
from app.core import ai_cover
from app.core.search_features import search_features
from app.core.content_normalization import canonical_text


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Selection(StrictBody):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["paper", "handout", "textbook"]
    subject: str = Field(default="", max_length=40)
    resource_ids: list[str] = Field(min_length=1, max_length=200)
    scores: list[float] = Field(default_factory=list, max_length=200)
    total_score: float | None = Field(default=None, ge=0, le=200000)


def create_selection(body: Selection, db, user):
    if len(set(body.resource_ids)) != len(body.resource_ids):
        raise HTTPException(422, "选题重复")
    if body.kind != "paper" and (body.scores or body.total_score is not None):
        raise HTTPException(422, "仅试卷支持分值")
    if body.scores and len(body.scores) != len(body.resource_ids):
        raise HTTPException(422, "分值数量与题目数量不一致")
    if body.total_score is not None and abs(sum(body.scores)-body.total_score) > 0.000001:
        raise HTTPException(422, "总分不符合要求")
    blocks = []
    for i, rid in enumerate(body.resource_ids):
        r = db.get(TeachingResource, rid)
        if not r or r.archived or r.kind not in ("question", "knowledge") or body.kind == "paper" and r.kind != "question":
            raise HTTPException(422, "选题资源不存在或类型不符")
        blocks.append(documents.Block(uid=str(uuid4()), kind="reference", resource_id=rid,
                                      score=body.scores[i] if body.scores else 0))
    return documents.create(documents.Draft(title=body.title, kind=body.kind,
                                            subject=body.subject, blocks=blocks), db, user)


class BlockPatch(StrictBody):
    uid: str = Field(min_length=1, max_length=36)
    field: Literal["title","content","answer","solution","analysis","proof","score","hidden_fields"]
    value: str | float | list[str]


class DocumentPatch(StrictBody):
    revision: int = Field(ge=1)
    patches: list[BlockPatch] = Field(min_length=1,max_length=100)


def patch_document(id: str, body: DocumentPatch, db, user):
    resources.admin_lock(db,user)
    d = documents.row(db,id)
    if d.kind == "intake" or d.chaptered or d.archived or d.revision != body.revision:
        raise HTTPException(409,"仅支持当前版本的创作文档局部编辑")
    blocks = [dict(b) for b in d.blocks]
    by_id = {b["uid"]: b for b in blocks}
    seen=set()
    for p in body.patches:
        b=by_id.get(p.uid)
        if not b or (p.uid,p.field) in seen:
            raise HTTPException(422,"修改对象不存在或重复")
        seen.add((p.uid,p.field))
        if p.field=="score":
            if d.kind!="paper" or b.get("snapshot",b).get("kind")!="question" or b.get("subquestion_scores") or not isinstance(p.value,(int,float)):
                raise HTTPException(422,"仅允许设置试卷整题分值")
        elif p.field=="hidden_fields":
            if b["kind"]!="reference" or not isinstance(p.value,list):
                raise HTTPException(422,"仅引用块可设置字段显示")
        else:
            if not isinstance(p.value,str) or b["kind"] not in ("heading","text","question","knowledge","reference"):
                raise HTTPException(422,"不支持该字段")
            if b["kind"]=="reference":
                b["local_fields"]=list(dict.fromkeys([*(b.get("local_fields") or []),p.field]))
            elif p.field not in documents.EDITABLE.get(b["kind"],set()):
                raise HTTPException(422,"不支持该字段")
        b[p.field]=p.value
    return documents.update(id,documents.Draft(title=d.title,kind=d.kind,subject=d.subject,source_id=d.source_id,
                                                blocks=blocks,revision=body.revision),db,user)


class AppendReferences(StrictBody):
    revision:int=Field(ge=1)
    resource_ids:list[str]=Field(min_length=1,max_length=200)
    scores:list[float]=Field(default_factory=list,max_length=200)

def append_references(id:str,body:AppendReferences,db,user):
    resources.admin_lock(db,user)
    d=documents.row(db,id)
    if d.archived or d.kind=="intake" or d.chaptered or d.revision!=body.revision:
        raise HTTPException(409,"请重新读取有效创作文档及版本")
    if len(d.blocks)+len(body.resource_ids)>200:
        raise HTTPException(422,"请使用分章教材或拆分文档")
    if len(set(body.resource_ids))!=len(body.resource_ids) or set(body.resource_ids)&{b.get("resource_id") for b in d.blocks}:
        raise HTTPException(422,"新增题目重复")
    if body.scores and (d.kind!="paper" or len(body.scores)!=len(body.resource_ids)):
        raise HTTPException(422,"分值与题目不匹配")
    blocks=[documents.Block.model_validate(b) for b in d.blocks]
    for i,rid in enumerate(body.resource_ids):
        r=db.get(TeachingResource,rid)
        if not r or r.archived or r.kind not in ("question","knowledge") or (d.kind=="paper" and r.kind!="question"):
            raise HTTPException(422,"引用资源无效")
        blocks.append(documents.Block(uid=str(uuid4()),kind="reference",resource_id=rid,score=body.scores[i] if body.scores else 0))
    return documents.update(id,documents.Draft(title=d.title,kind=d.kind,subject=d.subject,source_id=d.source_id,
                                               blocks=blocks,revision=body.revision),db,user)

class TemplateApply(StrictBody):
    revision:int=Field(ge=0)
    template_id:str=Field(min_length=1,max_length=80)

def apply_template(scope:Literal["doc","source"],identity:str,body:TemplateApply,db,user):
    record=settings.read_document_templates(db,user)
    template=next((v for v in record["value"] if v["id"]==body.template_id),None)
    if not template:raise HTTPException(404,"未找到用户排版模板")
    return settings.update_document_layout(scope,identity,settings.LayoutUpdate(revision=body.revision,value=template["layout"]),db,user)

class FormulaQuery(StrictBody):
    formula:str=Field(min_length=1,max_length=4000)
    subject:str=Field(default="",max_length=40)
    limit:int=Field(default=30,ge=1,le=100)
    offset:int=Field(default=0,ge=0)

def formula_search(body:FormulaQuery,db):
    # The existing GIN feature index matches formula shape, not mathematical equivalence.
    raw=body.formula.strip()
    if "$" not in canonical_text(raw):raw="$"+raw+"$"
    keys=[k for k in search_features(raw) if k.startswith("m:")]
    if not keys:raise HTTPException(422,"请输入有效LaTeX公式")
    stmt=select(TeachingResource).where(TeachingResource.kind=="question",TeachingResource.archived==False,
        TeachingResource.search_features.op("?")(keys[0]))
    if body.subject:stmt=stmt.where(TeachingResource.subject==resources.normalize_subject(body.subject))
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=db.scalars(stmt.order_by(TeachingResource.updated_at.desc(),TeachingResource.id).offset(body.offset).limit(body.limit))
    return {"items":[resources.view(r) for r in rows],"total":total,"offset":body.offset,
            "scope":"formula_shape_candidates","warning":"公式结构候选，不代表代数等价或重复题；多公式题可能需要关键词和标签辅助检索"}

class ReadOriginal(StrictBody):
    file_id: str=Field(min_length=1,max_length=36)
    start: int=Field(default=1,ge=1,le=10000)
    end: int=Field(default=1,ge=1,le=10000)
    mode: Literal["text","ocr"]="text"


def read_original(body: ReadOriginal, db, model="Auto", effort="default"):
    if body.end<body.start or body.end-body.start>=10:
        raise HTTPException(422,"单批最多读取10页或段")
    f=db.scalar(workspaces.original_query().where(StoredFile.id==body.file_id,StoredFile.archived==False))
    if not f:raise HTTPException(404,"原始资料不存在")
    if f.media_type in storage.IMAGE_TYPES or f.media_type=="application/pdf":
        # Long visual batches must use the checkpointed recognize action.
        if body.start!=body.end:raise HTTPException(422,"多页资料请使用recognize流程，逐页AI识别并合并，不要调用original_read")
        result=material_vision.recognize_range(f,body.start,body.end,model,effort)
    else:result=material_import.extract(f,"text",body.start,body.end)
    return {**result,"file_id":f.id,"name":f.name,"verified":False}


class HistoryQuery(StrictBody):
    q: str=Field(min_length=1,max_length=200)


def history_search(body: HistoryQuery,db):
    q=body.q.strip()
    if not q:raise HTTPException(422,"请输入历史检索词")
    sessions=list(db.scalars(select(ChatSession).where(ChatSession.title.contains(q,autoescape=True)|ChatSession.project.contains(q,autoescape=True)).order_by(ChatSession.updated_at.desc()).limit(10)))
    messages=list(db.scalars(select(ChatMessage).where(ChatMessage.state=="done",ChatMessage.content.contains(q,autoescape=True)).order_by(ChatMessage.created_at.desc()).limit(15)))
    work=list(db.scalars(select(WorkSession).where(WorkSession.title.contains(q,autoescape=True)).order_by(WorkSession.updated_at.desc()).limit(10)))
    return {"sessions":[{"id":s.id,"title":s.title,"project":s.project} for s in sessions],
            "messages":[{"id":m.id,"session_id":m.session_id,"role":m.role,"content":m.content[:1200]} for m in messages],
            "work":[{"id":s.id,"title":s.title,"recent":[{"instruction":r.get("instruction"),"state":r.get("state"),"detail":r.get("detail")} for r in (s.agent_history or [])[-3:]]} for s in work]}


class TextIntake(StrictBody):
    title: str=Field(min_length=1,max_length=200)
    subject: str=Field(default="",max_length=40)
    text: str=Field(min_length=1,max_length=24000)
    intent: Literal["mixed","question","knowledge","document"]="mixed"


def intake_text(body: TextIntake,db,user,model="Auto",effort="default"):
    from app.api import intelligence
    # Explicitly distinguish an AI-provided draft from original textbook material.
    request=intelligence.Start(**body.model_dump(),model=model,effort=effort,input_origin="chat_draft")
    return intelligence.start(request,db,user)


def intake_status(id: str,db):
    from app.api import intelligence
    return intelligence.detail(id,db)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: object
    schema: type
    fixed: dict
    write: bool

    def run(self, args, db, user, model=None, effort=None):
        validated = self.schema.model_validate(args)
        params = {key: getattr(validated, key) for key in type(validated).model_fields}
        params.update(self.fixed)
        signature = inspect.signature(self.handler)
        for name, value in signature.parameters.items():
            if name in params:
                continue
            if name == "db":
                params[name] = db
            elif name == "user":
                params[name] = user
            elif isinstance(value.default, FieldInfo):
                params[name] = value.default.default
            elif value.default is not inspect.Parameter.empty:
                params[name] = value.default
        if self.name in ("intake_text","original_read"):params.update(model=model or "Auto",effort=effort or "default")
        # Model selection is controlled by the task, not by generated arguments.
        if self.name in ("video_generate", "video_edit"):
            if self.name == "video_generate":
                params["body"] = video.InferenceOptions(model=model, effort=effort)
            else:
                params["body"] = video.Instruction(instruction=params.pop("instruction"), model=model, effort=effort)
        return jsonable_encoder(self.handler(**params))


TOOLS = {}


def register(name, description, handler, fields=(), *, fixed=None, write=False, custom=None):
    signature = inspect.signature(handler)
    definitions = {}
    for field in fields:
        p = signature.parameters[field]
        default = ... if p.default is inspect.Parameter.empty else p.default
        definitions[field] = (p.annotation, default)
    definitions.update(custom or {})
    schema = create_model("Tool_" + name, __base__=StrictBody, **definitions)
    TOOLS[name] = Tool(name, description, handler, schema, fixed or {}, write)


register("question_search", "题库精准筛选；返回真实记录及分页信息", resources.listing,
         ("subject","q","chapter","question_type","difficulty","source_id","source_ids","knowledge_id","knowledge_ids","year_from","year_to","method_name","limit","offset"),
         fixed={"kind":"question","archived":False,"compact":True,"bank_summary":True})
register("formula_search", "按LaTeX公式结构检索真实候选题；不是数学等价性证明",formula_search,("body",))
register("knowledge_search", "检索录入的知识点，不是知识标签", resources.listing,
         ("subject","q","chapter","unit_type","limit","offset"), fixed={"kind":"knowledge","archived":False})
register("resource_read", "读取真实题目或知识点及答案解析", resources.read, ("id",))
register("related_questions", "根据真实题干、解法与标签查询相关题目候选，不代表重复题", documents.related_questions, ("body",))
register("resource_methods", "读取已有解法", resources.methods, ("id",))
register("resource_sources", "读取题目来源", resources.list_sources, ("id",))
register("tag_search", "检索知识图谱标签", knowledge.list_points, ("q","subject","limit","offset"))
register("tag_neighbors", "读取知识标签关联", knowledge.tag_neighbors, ("id","limit","offset"))
register("source_search", "检索来源记录", resources.listing, ("q","subject","exam_type","source_type","catalog_institution","catalog_year","limit","offset"), fixed={"kind":"source","archived":False})
register("source_read", "读取来源信息", source_catalog.read, ("id",))
register("source_questions", "读取指定来源的题目", bank_work.source_questions, ("id","offset","limit"))
register("source_statistics", "按来源、年份、院校等统计实际已录入知识点", source_catalog.statistics, ("body",))
register("original_search", "查询原始资料库与识别进度", workspaces.library, ("q","limit","offset"), fixed={"archived":False})
register("original_read", "读取单页原图（AI视觉）或文本段；多页/试卷录入必须使用recognize流程", read_original, ("body",))
register("history_search", "按关键词查询历史聊天及工作记录", history_search, ("body",))
register("intake_text", "从用户提供的文字创建待人工审核的录入任务，不正式入库", intake_text, ("body",), write=True)
register("intake_status", "查看录入任务实际状态", intake_status, ("id",))
register("document_search", "查询教学资料", documents.listing, ("q","kind","limit","offset"), fixed={"archived":False})
register("document_read", "读取文档及真实版本", documents.read, ("id",))
register("book_chapters", "读取教材章节", documents.book_chapters, ("id",))
register("layout_read", "读取文档或来源排版设置", settings.read_document_layout, ("scope","identity"))
register("template_search", "查询用户排版模板", settings.read_document_templates)
register("work_search", "查询已归档教学作品", teaching_works.listing, ("q","kind","subject","scope","limit","offset"))
register("work_read", "读取教学作品实际版本", teaching_works.detail, ("ident",))
register("video_search", "查询视频项目", video.listing)
register("video_read", "查询视频实际状态与任务", video.detail, ("ident",))
register("video_code", "读取视频实际Manim源码",video.code,("ident",))
register("video_job_read","读取指定视频项目中的真实制作任务状态",video.job_read,("ident","job_id"))
register("video_history", "读取视频微调记录", video.history, ("ident",))
register("cover_templates", "读取封面和其他模板素材目录",studio.listing,("q","limit","offset"),fixed={"kind":"asset","category":"template","archived":False})
register("cover_presets", "查询现有封面预设", studio.presets)
register("cover_create", "生成可编辑的封面草稿，图层位置以画布百分比表示；不输出PNG或自动发布",ai_cover.create,("body",),write=True)
register("cover_search", "读取已保存的封面作品目录",studio.listing,("q","limit","offset"),fixed={"kind":"work","category":"cover","archived":False})
register("checkin_state", "查询实际签到状态", qiandao.status)
register("model_catalog", "查询模型及推理强度", qoder.models)
register("model_usage", "查询模型实际额度", qoder.usage)
register("selection_create", "从已存在题目或知识点创建试卷、讲义或教材草稿；不改原资源", create_selection,
         ("body",), write=True)
register("book_create", "创建教材或章节式讲义草稿", documents.create_book, ("body",), write=True)
register("chapter_create", "在指定教材中新增章节", documents.create_chapter, ("id","body"), write=True)
register("document_append", "向现有创作文档或教材章节追加真实引用题目；保留已有内容", append_references, ("id","body"),write=True)
register("chapter_order", "按实际章节ID调整目录顺序", documents.order_chapters, ("id","body"),write=True)
register("template_apply", "应用真实用户排版模板，需要当前排版revision", apply_template, ("scope","identity","body"),write=True)
register("document_patch", "按真实文档块编号局部修改创作文档，不修改题库原件；需要当前版本", patch_document, ("id","body"), write=True)
register("layout_update", "修改指定文档或来源排版配置，必须使用最新revision；不自动正式导出", settings.update_document_layout, ("scope","identity","body"), write=True)
register("video_create", "根据题库原题和已有推荐解析创建视频项目", video.create, ("body",), write=True)
register("video_generate", "提交指定视频的代码生成任务；原引擎生成校验成功后自动渲染，不重复提交渲染", video.produce, ("ident",), fixed={"action":"generate"}, write=True)
register("video_retry","重试已失败或取消的指定视频任务；引擎决定是否复用代码",video.job_action,("ident","job_id"),fixed={"action":"retry"},write=True)
register("video_render", "提交指定视频的渲染任务，不代表成片完成", video.produce, ("ident",), fixed={"action":"render"}, write=True)
register("video_edit", "提交指定视频的局部微调任务", video.edit, ("ident",),
         custom={"instruction":(str,Field(min_length=1,max_length=12000))}, write=True)


def catalogue(mode="work"):
    return [{"name":t.name,"description":t.description,"parameters":t.schema.model_json_schema(),
             "write":t.write} for t in TOOLS.values() if mode=="work" or not t.write]


def execute(name, args, db, user, *, mode="work", model=None, effort=None):
    tool=TOOLS.get(name)
    if not tool or mode not in ("work","chat") or mode=="chat" and tool.write:
        raise HTTPException(403,"工具不存在或当前模式无权限")
    return tool.run(args,db,user,model,effort)


def bounded_result(value, limit=12000):
    raw=json.dumps(value,ensure_ascii=False,default=str)
    if len(raw)<=limit:
        return value
    # Preserve IDs and pagination metadata instead of chopping JSON arbitrarily.
    if isinstance(value,dict):
        result={k:(v[:2400] if isinstance(v,str) else v) for k,v in value.items() if not isinstance(v,(dict,list)) and k not in ("password","token","pat")}
        if len(json.dumps(result,ensure_ascii=False,default=str))>limit//2:
            result={k:(v[:600] if isinstance(v,str) else v) for k,v in result.items()}
        rows=next((v for k,v in value.items() if k in ("items","rows","results","blocks","jobs") and isinstance(v,list)),[])
    elif isinstance(value,list):
        result={};rows=value
    else:
        return {"truncated":True,"preview":raw[:limit-100]}
    if isinstance(value,dict) and isinstance(value.get("lesson"),dict):
        result["lesson"]={k:v for k,v in value["lesson"].items() if k in ("id","status","state","revision","has_video","video_review_status","code_status","render_status")}
    result.update(truncated=True,items=[])
    for row in rows:
        if isinstance(row,dict):
            item={k:v[:600] if isinstance(v,str) else v for k,v in row.items()
                  if k in ("id","uid","code","title","kind","subject","revision","name","state","status","resource_id","question_type","difficulty","question_count","source_question_count","content","answer","solution","score","start","end")}
        else:
            item=str(row)[:300]
        if len(json.dumps(result,ensure_ascii=False,default=str))+len(json.dumps(item,ensure_ascii=False,default=str))>limit-500:
            break
        result["items"].append(item)
    return result
