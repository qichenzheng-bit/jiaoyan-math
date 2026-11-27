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
from app.models import TeachingResource


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
         fixed={"kind":"question","archived":False,"compact":True})
register("knowledge_search", "检索录入的知识点，不是知识标签", resources.listing,
         ("subject","q","chapter","unit_type","limit","offset"), fixed={"kind":"knowledge","archived":False})
register("resource_read", "读取真实题目或知识点及答案解析", resources.read, ("id",))
register("resource_methods", "读取已有解法", resources.methods, ("id",))
register("resource_sources", "读取题目来源", resources.list_sources, ("id",))
register("tag_search", "检索知识图谱标签", knowledge.list_points, ("q","subject","limit","offset"))
register("tag_neighbors", "读取知识标签关联", knowledge.tag_neighbors, ("id","limit","offset"))
register("source_search", "检索来源记录", resources.listing, ("q","subject","exam_type","source_type","catalog_institution","catalog_year","limit","offset"), fixed={"kind":"source","archived":False})
register("source_read", "读取来源信息", source_catalog.read, ("id",))
register("source_questions", "读取指定来源的题目", bank_work.source_questions, ("id","offset","limit"))
register("source_statistics", "按来源、年份、院校等统计实际已录入知识点", source_catalog.statistics, ("body",))
register("original_search", "查询原始资料库与识别进度", workspaces.library, ("q","limit","offset"), fixed={"archived":False})
register("document_search", "查询教学资料", documents.listing, ("q","kind","limit","offset"), fixed={"archived":False})
register("document_read", "读取文档及真实版本", documents.read, ("id",))
register("book_chapters", "读取教材章节", documents.book_chapters, ("id",))
register("layout_read", "读取文档或来源排版设置", settings.read_document_layout, ("scope","identity"))
register("template_search", "查询用户排版模板", settings.read_document_templates)
register("video_search", "查询视频项目", video.listing)
register("video_read", "查询视频实际状态与任务", video.detail, ("ident",))
register("video_history", "读取视频微调记录", video.history, ("ident",))
register("cover_presets", "查询现有封面预设", studio.presets)
register("checkin_state", "查询实际签到状态", qiandao.status)
register("model_catalog", "查询模型及推理强度", qoder.models)
register("model_usage", "查询模型实际额度", qoder.usage)
register("selection_create", "从已存在题目或知识点创建试卷、讲义或教材草稿；不改原资源", create_selection,
         ("body",), write=True)
register("book_create", "创建教材或章节式讲义草稿", documents.create_book, ("body",), write=True)
register("chapter_create", "在指定教材中新增章节", documents.create_chapter, ("id","body"), write=True)
register("video_create", "根据题库原题和已有推荐解析创建视频项目", video.create, ("body",), write=True)
register("video_generate", "提交指定视频的代码生成任务，不代表渲染完成", video.produce, ("ident",), fixed={"action":"generate"}, write=True)
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
        result={k:v for k,v in value.items() if not isinstance(v,(dict,list)) and len(str(v))<500}
        rows=next((v for k,v in value.items() if k in ("items","rows","results","blocks","jobs") and isinstance(v,list)),[])
    elif isinstance(value,list):
        result={};rows=value
    else:
        return {"truncated":True,"preview":raw[:limit-100]}
    result.update(truncated=True,items=[])
    for row in rows:
        if isinstance(row,dict):
            item={k:v[:600] if isinstance(v,str) else v for k,v in row.items()
                  if k in ("id","code","title","kind","subject","revision","name","state","status","resource_id","question_type","difficulty","question_count","source_question_count","content","start","end")}
        else:
            item=str(row)[:300]
        if len(json.dumps(result,ensure_ascii=False,default=str))+len(json.dumps(item,ensure_ascii=False,default=str))>limit-500:
            break
        result["items"].append(item)
    return result
