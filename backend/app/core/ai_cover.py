"""Validated editable cover drafts. Never publish or render on behalf of the user."""
from typing import Literal
from uuid import uuid4
import json
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.api import studio
from app.models import TeachingResource

Color = str

class Layer(BaseModel):
    model_config=ConfigDict(extra="forbid",allow_inf_nan=False)
    kind:Literal["text","math","question","logo","rectangle","ellipse","line"]
    content:str=Field(default="",max_length=4000)
    resource_id:str|None=Field(default=None,max_length=36)
    x:float=Field(ge=0,le=100)
    y:float=Field(ge=0,le=100)
    w:float=Field(gt=0,le=100)
    h:float=Field(gt=0,le=100)
    font:int=Field(default=48,ge=8,le=400)
    color:Color=Field(default="#242424",pattern=r"^#[a-fA-F0-9]{6}$")
    fill:Color=Field(default="#DCECE5",pattern=r"^#[a-fA-F0-9]{6}$")
    align:Literal["left","center","right"]="center"
    weight:Literal[400,500,600,700]=400

class CoverDraft(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(min_length=1,max_length=200)
    format:Literal["xiaohongshu","douyin","douyin_wide","douyin_full","bilibili","bilibili_wide","wechat_top","wechat_sub"]
    background:Color=Field(default="#ffffff",pattern=r"^#[a-fA-F0-9]{6}$")
    layers:list[Layer]=Field(min_length=1,max_length=20)

def build(body,db):
    w,h,*_=studio.PRESETS[body.format]
    layers=[]
    names={"text":"文字","math":"公式","question":"题干","logo":"品牌 Logo","rectangle":"矩形","ellipse":"圆形","line":"直线"}
    for layer in body.layers:
        if layer.x+layer.w>100.00001 or layer.y+layer.h>100.00001:
            raise HTTPException(422,"封面元素超出画布")
        content=layer.content
        if layer.kind=="question":
            r=db.get(TeachingResource,layer.resource_id) if layer.resource_id else None
            if not r or r.archived or r.kind!="question":
                raise HTTPException(422,"请选择真实题库题目")
            content=r.content
            if len(content)>4000:raise HTTPException(422,"题干过长，请先在工作台确定封面展示范围")
        elif layer.resource_id:
            raise HTTPException(422,"仅题干图层允许引用题库")
        elif layer.kind in ("logo","rectangle","ellipse","line"):
            content=""
        if layer.kind in ("text","math","question") and not content.strip():
            raise HTTPException(422,"文字图层不能为空")
        layers.append({"id":str(uuid4()),"kind":layer.kind,"name":names[layer.kind],"content":content,
            "x":round(w*layer.x/100),"y":round(h*layer.y/100),"w":max(1,round(w*layer.w/100)),
            "h":max(1,round(h*layer.h/100)),"font":layer.font,"color":layer.color,"fill":layer.fill,
            "align":layer.align,"weight":layer.weight,"rotation":0,"opacity":100,"hidden":False,"locked":False,
            **({"resourceId":layer.resource_id} if layer.resource_id else {})})
    return {"version":1,"name":body.name,"format":body.format,"width":w,"height":h,
            "background":body.background,"layers":layers}

def create(body:CoverDraft,db,user):
    design=build(body,db)
    content=json.dumps(design,ensure_ascii=False)
    if len(content)>50000:raise HTTPException(422,"封面草稿过长")
    row=studio.create(studio.Draft(kind="work",title=body.name,
          data={"category":"cover","content":content,"note":"AI 可编辑草稿；待检查及导出"}),db,user)
    return {"id":row["id"],"title":row["title"],"kind":"cover","revision":row["revision"],
            "state":"draft","detail":"已保存可编辑封面草稿，尚未渲染或导出"}
