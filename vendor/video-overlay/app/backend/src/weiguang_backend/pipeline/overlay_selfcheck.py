#!/usr/bin/env python3
"""One-shot isolated test of installed engine dependencies and actual source APIs.
No AI calls, databases, user data, generated scene execution, or pressure tests.
Use --captions to test actual Manim/LaTeX caption object construction only.
"""
import argparse
import ast
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
if __name__=="__main__":main()
