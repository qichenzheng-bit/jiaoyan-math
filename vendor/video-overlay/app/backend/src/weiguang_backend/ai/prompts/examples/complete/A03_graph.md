### 示例四：数形结合与定积分应用（左图右推 · 直观衔接）

```python title=scene_04
from manim import *
from animation_engine.code.authored_scene import AuthoredScene
from animation_engine.code.board_kit import (
    HIGHLIGHT_BLUE, INK_BLACK, aside_card, board_bounds,
    integral_area_with_sweep, math_axes_box, mixed_text, two_column_frame,
)


class IntegralAreaExample(AuthoredScene):
    def construct(self):
        self.camera.background_color = "#FFFFFF"
        bounds = board_bounds()
        stem = VGroup(
            mixed_text(("t", "求曲线 "), ("m", r"y=x^2"), ("t", " 与 "), ("m", r"y=x"), ("t", " 所围成平面图形的面积 "), ("m", r"S"), ("t", "。"), font_size=28, color=INK_BLACK),
        ).move_to([0.0, 0.35, 0.0])

        self.start_cue(
            "geo_01",
            "同学们，求平面图形面积一定要先画草图定清上下边界。来看题目：求 y=x^2 与 y=x 围成图形的面积 S。",
            "",
            tts_text="同学们，求平面图形面积一定要先画草图定清上下边界。来看题目：求 y 等于 x 平方与 y 等于 x 围成图形的面积 S。",
        )
        self.play(FadeIn(stem), run_time=min(0.65, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("geo_01")

        stem_top = stem.copy().scale(0.82)
        stem_top.move_to([max(bounds["stem_left_x"] + stem_top.width / 2.0, min(0.0, bounds["stem_right_x"] - stem_top.width / 2.0)), min(3.55, bounds["stem_top_y"]) - stem_top.height / 2.0, 0.0])

        axes, axes_grp = math_axes_box([0, 1.35, 0.5], [0, 1.35, 0.5], x_length=4.4, y_length=3.3)
        area_grp = integral_area_with_sweep(
            axes, lambda x: x ** 2, lambda x: x, (0.0, 1.0),
            sweep_x=0.55, lower_label=r"y=x^2", upper_label=r"y=x",
        )
        diagram = VGroup(axes_grp, area_grp)

        s1 = MathTex(r"x^2 = x \Longrightarrow x_1 = 0,\; x_2 = 1", color=INK_BLACK).scale(0.70)
        s2 = MathTex(r"S = \int_0^1 (x - x^2)\,\mathrm{d}x", color=INK_BLACK).scale(0.70)
        s3 = MathTex(r"= \left[\frac{1}{2}x^2 - \frac{1}{3}x^3\right]_0^1 = \frac{1}{6}", color=INK_BLACK).scale(0.70)
        work = VGroup(s1, s2, s3).arrange(DOWN, aligned_edge=LEFT, buff=0.34)
        two_column_frame(
            diagram, work,
            top_y=stem_top.get_bottom()[1] - 0.38,
            bottom_y=bounds["board_floor_y"],
            left_x=bounds["left_x"],
            right_x=bounds["right_x"],
            align_top=True,
        )

        self.start_cue(
            "geo_02",
            "先画坐标系与两条边界曲线，再联立方程 x^2 = x，算出交点横坐标是 x=0 和 x=1。",
            "",
            pause_before_seconds=0.45,
            tts_text="先画坐标系与两条边界曲线，再联立方程 x 平方等于 x，算出交点横坐标是 x 等于 0 和 x 等于 1。",
        )
        self.play(Transform(stem, stem_top), run_time=min(0.45, max(0.1, self.cue_time_left() * 0.20)))
        self.play(FadeIn(axes_grp), Create(area_grp[1]), Create(area_grp[2]), FadeIn(area_grp[4]), FadeIn(area_grp[5]), Write(s1), run_time=min(1.0, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("geo_02")

        self.start_cue(
            "geo_03",
            "看图一目了然：在区间 (0, 1) 上直线 y=x 压在抛物线 y=x^2 上方。所以用上曲线减下曲线从 0 积到 1。",
            "",
            tts_text="看图一目了然：在区间 0 到 1 上直线 y 等于 x 压在抛物线 y 等于 x 平方上方。所以用上曲线减下曲线从 0 积到 1。",
        )
        self.play(FadeIn(area_grp[0]), Create(area_grp[3]), Write(s2), run_time=min(0.85, max(0.1, self.cue_time_left() * 0.50)))
        self.end_cue("geo_03")

        self.start_cue(
            "geo_04",
            "分别求出原函数二分之一 x^2 减三分之一 x^3，代入上下限计算得面积等于 1/6。",
            "",
            tts_text="分别求出原函数二分之一 x 平方减三分之一 x 立方，代入上下限计算得面积等于六分之一。",
        )
        self.play(Write(s3), run_time=min(0.80, max(0.1, self.cue_time_left() * 0.45)))
        box = SurroundingRectangle(s3, color=HIGHLIGHT_BLUE, buff=0.08)
        self.play(Create(box), run_time=min(0.32, max(0.05, self.cue_time_left() * 0.25)))
        self.check_layout("积分结果", question=stem, diagram=diagram, working=VGroup(work, box))
        self.end_cue("geo_04")

        summary = aside_card(
            "方法与注意点总结",
            [("t", "1. 先联立求交点定上下限，再画草图判别上下曲线顺序。")],
            [("t", "2. 面积微元公式："), ("m", r"\mathrm{d}S=(y_{\text{top}}-y_{\text{bot}})\,\mathrm{d}x"), ("t", "（若横向更简则换用 "), ("m", r"\mathrm{d}y"), ("t", "）。")],
            [("t", "3. 易错警示：上下曲线反减会算成负面积。")],
            kind="summary",
            width=11.4,
            title_size=26,
            body_size=24,
            line_buff=0.22,
        )
        summary.next_to(stem, DOWN, buff=0.42).set_x(0.0)

        self.start_cue(
            "geo_05",
            "最后总结：求平面图形面积先找交点定积分限，再借助草图用上减下立式，确保被积函数非负。",
            "",
            pause_before_seconds=0.45,
            tts_text="最后总结：求平面图形面积先找交点定积分限，再借助草图用上减下立式，确保被积函数非负。",
        )
        self.play(FadeOut(VGroup(diagram, work, box)), run_time=min(0.28, max(0.05, self.cue_time_left() * 0.15)))
        self.play(FadeIn(summary), run_time=min(0.70, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("geo_05")
```
