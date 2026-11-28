# C01 scene

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

from manim import *
from animation_engine.code.authored_scene import AuthoredScene
class LessonScene(AuthoredScene):
    def construct(self):
        self.camera.background_color = WHITE
        self.start_cue("s01_open","今天来看一道例题。","")
        self.end_cue("s01_open")
