import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location("native_video_smoke",Path(__file__).resolve().parents[2]/"deploy"/"native-video-smoke.py")
smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)

def test_synthetic_video_code_is_parsed_not_executed():
    smoke.validate_code("from manim import *\nclass SmokeScene(Scene):\n    def construct(self):\n        self.add(MathTex('1+1=2'))")
    with pytest.raises(ValueError):smoke.validate_code("x=1")
    with pytest.raises(SyntaxError):smoke.validate_code("not valid python !!!")
