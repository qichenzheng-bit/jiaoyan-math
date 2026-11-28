"""Versioned question structure; old text stays the lossless compatibility contract."""
import hashlib
import json
import re
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.core.solution_methods import parse_methods, format_methods

CHOICE={"选择题","单选题","多选题"}
OPTION=re.compile(r"^([A-Z])[.、)]\s+(.*)$")
SUB=re.compile(r"^[（(]([1-9][0-9]*)[）)]\s*(.*)$")
# In answer/solution text, a reference to an existing numbered formula is not a new subquestion.
SUB_RESULT=re.compile(r"^[（(]([1-9][0-9]*)[）)](?!\s*(?:式|中的|中可|所示|所述|可知|可得|得出|成立|的结论|的结果))\s*(.*)$")
BLANK=r"$\underline{\qquad}$"
TEXT_FIELDS=("content","answer","solution")

class Method(BaseModel):
    body:str=Field(default="",max_length=50000)
    name:str=Field(default="",max_length=120)
    recommended:bool=False

class Option(BaseModel):
    label:str=Field(pattern=r"^[A-Z]$")
    content:str=Field(default="",max_length=50000)

class Part(BaseModel):
    number:int=Field(ge=1,le=30)
    content:str=Field(default="",max_length=50000)
    answer:str=Field(default="",max_length=20000)
    methods:list[Method]=Field(default_factory=list,max_length=30)

class Blank(BaseModel):
    number:int=Field(ge=1,le=100)
    answer:str=Field(default="",max_length=20000)

class QuestionData(BaseModel):
    version:Literal[1]=1
    stem:str=Field(default="",max_length=50000)
    options:list[Option]=Field(default_factory=list,max_length=26)
    correct_options:list[str]=Field(default_factory=list,max_length=26)
    subquestions:list[Part]=Field(default_factory=list,max_length=30)
    blanks:list[Blank]=Field(default_factory=list,max_length=100)
    answer:str=Field(default="",max_length=20000)
    methods:list[Method]=Field(default_factory=list,max_length=30)
    warnings:list[str]=Field(default_factory=list,max_length=10)
    legacy_digest:str|None=Field(default=None,pattern=r"^[a-f0-9]{64}$")
    @model_validator(mode="after")
    def validate_shape(self):
        labels=[o.label for o in self.options]
        if labels!=[chr(65+i) for i in range(len(labels))]:
            raise ValueError("选项编号必须连续且不得重复")
        if len(self.correct_options)!=len(set(self.correct_options)) or not set(self.correct_options)<=set(labels):
            raise ValueError("答案选项不存在或重复")
        if self.correct_options and self.answer:raise ValueError("不得同时使用选项答案与文本答案")
        if sum(bool(v) for v in (self.options,self.subquestions,self.blanks))>1:
            raise ValueError("题型结构互相冲突")
        for parts in (self.subquestions,self.blanks):
            if [p.number for p in parts]!=list(range(1,len(parts)+1)):
                raise ValueError("小问或空位编号必须连续")
        if self.subquestions and (self.answer or self.methods):
            raise ValueError("含小问题目不得设置公共答案或解析")
        if self.blanks and (self.answer or self.stem.count(BLANK)!=len(self.blanks)):
            raise ValueError("空位和答案不一致")
        for group in (self.methods,*(part.methods for part in self.subquestions)):
            eligible=[m for m in group if m.body.strip()]
            preferred=next((m for m in eligible if m.recommended),eligible[0] if eligible else None)
            for method in group:method.recommended=method is preferred
        return self

def digest(content,answer,solution,question_type=""):
    return hashlib.sha256(json.dumps([content,answer,solution,question_type],ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def methods(raw):
    rows=parse_methods(raw)
    # A long legacy list is retained as one complete body instead of truncating it.
    if len(rows)>30:return [Method(body=raw,recommended=True)]
    return [Method(body=m["body"],recommended=m["recommended"]) for m in rows]

def method_text(rows):
    return format_methods([{"body":(m.name+"\n"+m.body if m.name and m.body else m.body),"recommended":m.recommended} for m in rows])

def project(data):
    content=data.stem;answer=data.answer;solution=method_text(data.methods)
    if data.options:
        content="\n".join([content,*[o.label+". "+o.content for o in data.options]]).strip()
        if data.correct_options:answer="".join(data.correct_options)
    if data.subquestions:
        content="\n".join([content,*["("+str(p.number)+")"+(" "+p.content if p.content else "") for p in data.subquestions]]).strip()
        answer="\n".join("("+str(p.number)+") "+p.answer for p in data.subquestions if p.answer)
        solution="\n".join("("+str(p.number)+") "+method_text(p.methods) for p in data.subquestions if method_text(p.methods))
    if data.blanks:
        answer=data.blanks[0].answer if len(data.blanks)==1 else "\n".join("("+str(p.number)+") "+p.answer for p in data.blanks if p.answer)
    return {"content":content,"answer":answer,"solution":solution}

def split_marked(raw,pattern):
    main=[];parts={};current=None;order=[]
    for line in raw.split("\n"):
        match=pattern.match(line)
        if match:
            current=match[1]
            if current in parts:return None
            order.append(current);parts[current]=[match[2]]
        elif current is None:main.append(line)
        else:parts[current].append(line)
    return "\n".join(main),{k:"\n".join(v) for k,v in parts.items()},order

def derive(content,answer,solution,question_type=""):
    mark=digest(content,answer,solution,question_type)
    warnings=[]
    fallback=lambda:QuestionData(stem=content,answer=answer,methods=methods(solution),warnings=warnings,legacy_digest=mark)
    if question_type in CHOICE:
        parsed=split_marked(content,OPTION)
        if parsed:
            main,parts,order=parsed
            if len(order)>=2 and order==[chr(65+i) for i in range(len(order))]:
                letters=list(dict.fromkeys(re.findall(r"[A-Z]",answer))) if re.fullmatch(r"[A-Z\s,，、]*",answer) else []
                if not set(letters)<=set(order) or question_type=="单选题" and len(letters)>1:
                    warnings.append("原答案选项存在歧义，保留原文待核对");letters=[]
                return QuestionData(stem=main,options=[Option(label=k,content=parts[k]) for k in order],correct_options=letters,answer="" if letters else answer,methods=methods(solution),warnings=warnings,legacy_digest=mark)
        warnings.append("选项未能可靠拆分，保留原始题干")
        return fallback()
    if question_type=="填空题":
        count=content.count(BLANK)
        if 1<=count<=100:
            if count==1:return QuestionData(stem=content,blanks=[Blank(number=1,answer=answer)],methods=methods(solution),legacy_digest=mark)
            parsed=split_marked(answer,SUB)
            if not answer.strip() or parsed and not parsed[0].strip() and set(parsed[2])<=set(str(i) for i in range(1,count+1)):
                return QuestionData(stem=content,blanks=[Blank(number=i,answer=parsed[1].get(str(i),"") if parsed else "") for i in range(1,count+1)],methods=methods(solution),legacy_digest=mark)
            warnings.append("多空答案对应关系不明确，保留原文待核对")
        return fallback()
    stem=split_marked(content,SUB);ans=split_marked(answer,SUB_RESULT);sol=split_marked(solution,SUB_RESULT)
    if stem and stem[2]:
        keys=stem[2]
        if len(keys)<=30 and keys==[str(i) for i in range(1,len(keys)+1)] and ans and sol and not ans[0].strip() and not sol[0].strip() and set(ans[2]+sol[2])<=set(keys):
            return QuestionData(stem=stem[0],subquestions=[Part(number=int(k),content=stem[1][k],answer=ans[1].get(k,""),methods=methods(sol[1].get(k,""))) for k in keys],legacy_digest=mark)
        warnings.append("小问编号或公共答案存在歧义，保留原文待核对")
    elif stem is None or (ans and ans[2]) or (sol and sol[2]):
        warnings.append("小问与答案无法可靠对应，保留原文待核对")
    return fallback()

def resolve(content,answer,solution,question_type="",stored=None):
    if stored:
        try:
            data=QuestionData.model_validate(stored)
            if data.legacy_digest==digest(content,answer,solution,question_type):return data
        except (ValueError,TypeError):pass
    return derive(content,answer,solution,question_type)

def normalize_payload(value):
    if not isinstance(value,dict):return value
    value=dict(value)
    if value.get("kind")!="question":
        value["question_data"]=None
        return value
    raw=value.get("question_data");typ=value.get("question_type") or ""
    legacy={k:value.get(k,"") for k in TEXT_FIELDS}
    if not all(isinstance(v,str) for v in legacy.values()):return value
    if raw:
        data=QuestionData.model_validate(raw)
        if data.legacy_digest is None:
            if data.warnings:raise ValueError("显式题目结构不能声明旧数据警告")
            if data.options and typ not in CHOICE or data.blanks and typ!="填空题" or data.subquestions and typ in CHOICE|{"填空题"}:
                raise ValueError("题型与结构不一致")
            if typ=="单选题" and len(data.correct_options)>1:raise ValueError("单选题最多一个正确选项")
            projected=project(data)
            if any(legacy[k] and legacy[k]!=projected[k] for k in TEXT_FIELDS):raise ValueError("结构化题目与兼容文本不一致")
            value.update(projected)
            value["question_data"]=data.model_copy(update={"legacy_digest":digest(**projected,question_type=typ)}).model_dump()
            return value
        if data.legacy_digest==digest(**legacy,question_type=typ) and project(data)==legacy:
            value["question_data"]=data.model_dump()
            return value
    value["question_data"]=derive(**legacy,question_type=typ).model_dump()
    return value
