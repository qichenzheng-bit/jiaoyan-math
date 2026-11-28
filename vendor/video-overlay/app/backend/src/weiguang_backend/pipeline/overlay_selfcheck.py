#!/usr/bin/env python3
"""One-shot isolated test of installed engine dependencies and actual source APIs.
No AI calls, databases, user data, generated scene execution, or pressure tests.
Use --captions to test actual Manim/LaTeX caption object construction only.
"""
import argparse
import ast
import json
from pathlib import Path
import tempfile

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--captions",action="store_true")
    args=parser.parse_args(argv)
    from animation_engine.core.video_settings import VIDEO_WIDTH,VIDEO_HEIGHT,DEFAULT_VIDEO_FPS,CAPTION_BAND_HEIGHT_PX
    from animation_engine.code.board_kit import board_bounds,fit_into_region,two_column_frame
    from animation_engine.render.layout_constraints import layout_prompt_fields
    from animation_engine.errors import EngineError
    from manim import Rectangle
    from weiguang_backend.pipeline import prompt_bundle
    from weiguang_backend.pipeline.edit_executor import assert_only_tts_text_changed,validate_edit_scope_ast,EditOutputError
    from weiguang_backend.pipeline.scene_codegen import load_shared_prompt_specs
    from weiguang_backend.pipeline.source_assets import prepare_lesson_source
    from weiguang_backend.pipeline import scene_edit,edit_render_repair,runtime_render_repair
    assert (VIDEO_WIDTH,VIDEO_HEIGHT,DEFAULT_VIDEO_FPS,CAPTION_BAND_HEIGHT_PX)==(1920,1080,60,240)
    fields=layout_prompt_fields()
    bounds=board_bounds(**fields)
    assert fields["watermark_safe_region_px"]["rect"]["width"]==260
    assert abs(bounds["stem_top_y"]-3.65)<0.001
    obj=Rectangle(width=5,height=1)
    fit_into_region(obj,top_y=1,bottom_y=-1,left_x=-2.25,right_x=2.25)
    try:fit_into_region(obj,top_y=1,bottom_y=-1,left_x=-1.8,right_x=1.8)
    except EngineError:pass
    else:raise AssertionError("cumulative scale floor")
    a,b=Rectangle(width=8,height=1),Rectangle(width=8,height=1)
    try:two_column_frame(a,b,top_y=2,bottom_y=-2,left_x=-5,right_x=5)
    except EngineError:pass
    else:raise AssertionError("overflow not rejected")
    src=prepare_lesson_source("求 x 的导数","利用基本公式得 1","1")
    with tempfile.TemporaryDirectory() as tmp:
        system=prompt_bundle.snapshot(src,src.prompt_payload(fps=60),Path(tmp))
        assert "不得依赖或主动播报试卷来源" in system
        assert len(load_shared_prompt_specs())>1000
        assert prompt_bundle.repair_system(tmp,"技术错误")
    old='class Demo(AuthoredScene):\n    def construct(self):\n        self.start_cue("c1","得","",tts_text="dei")\n        self.end_cue("c1")\n'
    new=old.replace('"dei"','"de"')
    assert_only_tts_text_changed({"scene_01":old},{"scene_01":new})
    try:validate_edit_scope_ast({"scene_01":old,"scene_02":old},{"scene_01":new},targets=("scene_01",))
    except EditOutputError:pass
    else:raise AssertionError("unauthorized scene deletion")
    check_knowledge_pipeline()
    print("VIDEO_OVERLAY_INTERFACE_CHECK_PASSED")
    if args.captions:
        from animation_engine.speech import spoken_captions as sc
        from animation_engine.speech.subtitle_style import normalize_subtitle_style
        # Same actual caption builder; no lesson execution or AI.
        cases=[("text","根据积分公式求导", ""),("math",r"\frac{\frac{1}{x}+\frac{1}{y}}{\sqrt{1+x^2}}",""),("math",r"\lim\limits_{x\to0}\frac{\ln(1+x)-x}{x^2}","")]
        for scale in (1.0,1.4):
            for kind,display,math in cases:
                try:
                    plate,glyph=sc._caption_frame(kind,display,normalize_subtitle_style({"font_scale":scale}),math=math)
                except EngineError as exc:
                    print("CAPTION_CASE_REQUIRES_REVIEW",scale,kind,str(exc));continue
                height=plate.height*135
                print("CAPTION_CASE",scale,kind,round(height,1),"px","fits-200" if height<=186.5 else "keep-240")
        print("CAPTION_OBJECT_CHECK_COMPLETE; production band unchanged")

def check_knowledge_pipeline():
    """Actual installed generation and static validation, with local model fixture."""
    from weiguang_backend.pipeline import prompt_bundle
    from weiguang_backend.pipeline.source_assets import prepare_lesson_source, KNOWLEDGE_PREFIX, actual_knowledge_type
    from weiguang_backend.pipeline.scene_codegen import generate_scene_sources, build_contract, extract_blocks
    from weiguang_backend.pipeline.scene_repair_support import _repair_prompt
    from animation_engine.code.scene_validator import validate_contract, validate_scene_source, validate_lesson_sources

    source_code = '''from manim import *
from animation_engine.code.authored_scene import AuthoredScene

class SmokeLesson(AuthoredScene):
    def construct(self):
        self.camera.background_color = WHITE
        self.start_cue("smoke_01", "这是一条静态接口测试口播。", "", tts_text="这是一条静态接口测试口播。")
        self.play(Write(Text("静态测试", color=BLACK)), run_time=min(0.4, self.cue_time_left()*0.4))
        self.end_cue("smoke_01")
'''
    for expected, proof, questions in (
        ("with_proof", "原文证明", [{"id":"linked-1","title":"关联例题","content":"例题正文","answer":"答案","solution":"解析"}]),
        ("without_proof", "", []),
        ("auto", "", [{"id":"linked-2","title":"关联例题二","content":"例题正文","answer":"答案","solution":"解析"}]),
    ):
        unit={"schema":"knowledge-video-source-v1","business_type":"knowledge",
              "teaching_type":expected,"title":"测试知识单元","content":"测试定义","proof":proof,
              "related_questions":questions,"association_count":len(questions),"teaching_detail":{}}
        raw=KNOWLEDGE_PREFIX+json.dumps(unit,ensure_ascii=False)
        source=prepare_lesson_source(unit["content"],raw)
        class Fixture:
            def generate_text(self, *, system, user_json, **kwargs):
                payload=json.loads(user_json)
                assert payload["business_type"]=="knowledge"
                assert payload["knowledge_unit"]["related_questions"]==questions
                assert "reference_solution" not in payload
                assert "不得另行生成、搜索其他题" in system
                if expected=="with_proof":assert "无证明专项" not in system
                if expected=="without_proof":assert "含证明专项" not in system
                return "\x60\x60\x60python title=scene_01\n# KNOWLEDGE_TEACHING_TYPE: "+("without_proof" if expected=="auto" else expected)+"\n"+source_code+"\n\x60\x60\x60"
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            generated=generate_scene_sources(source=source,client=Fixture(),output_dir=folder,fps=60)
            contract=build_contract(generated,question=source.problem,fps=60,extra_meta={"source_sha256":source.source_sha256})
            assert not validate_contract(contract)
            assert actual_knowledge_type(source,folder/"scenes")==("without_proof" if expected=="auto" else expected)
            data=json.loads((folder/"prompt_snapshot.json").read_text())
            assert data["business_type"]=="knowledge"
            assert data["source_sha256"]==source.source_sha256
            repair=json.loads(_repair_prompt(source,["[scene_01] test"],generated.sources,fps=60))
            assert repair["knowledge_unit"]["related_questions"]==questions
            assert "reference_solution" not in repair
    records=json.loads((prompt_bundle.PROMPTS_DIR/"examples/index.json").read_text())
    complete=[x for x in records if x.get("scope") in ("with_proof","without_proof") and x["kind"]=="complete"]
    assert len(complete)==12
    for rec in complete:
        text=(prompt_bundle.PROMPTS_DIR/"examples"/rec["path"]).read_text()
        blocks=extract_blocks(text)
        assert blocks,rec["id"]
        validated={name:validate_scene_source(code) for name,code in blocks}
        for name,result in validated.items():
            assert result.ok, rec["id"]+" "+name+" "+result.error_text()
        errors,_=validate_lesson_sources(validated)
        assert not errors,rec["id"]
    print("KNOWLEDGE_VIDEO_STATIC_CHECK_PASSED",len(complete))

if __name__=="__main__":main()
