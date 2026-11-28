### 示例三：概率论选择题（保留四选项 + 严谨条件核对）

```python title=scene_03
from manim import *
from animation_engine.code.authored_scene import AuthoredScene
from animation_engine.code.board_kit import (
    HIGHLIGHT_BLUE, INK_BLACK, aside_card,
    board_bounds, highlight_clause, mcq_options_grid, mixed_text,
)


class ProbMcqExample(AuthoredScene):
    def construct(self):
        self.camera.background_color = "#FFFFFF"
        bounds = board_bounds()
        q_line = mixed_text(("t", "设随机变量 "), ("m", r"X \sim N(1, 4)"), ("t", "，则 "), ("m", r"D(2X - 3) ="), font_size=27, color=INK_BLACK)
        opts = mcq_options_grid(
            [MathTex(r"(A)\; 5"), MathTex(r"(B)\; 8"), MathTex(r"(C)\; 13"), MathTex(r"(D)\; 16")],
            max_width=10.4,
            font_size=26,
        )
        stem = VGroup(q_line, opts).arrange(DOWN, aligned_edge=LEFT, buff=0.24)
        stem.move_to([0.0, 0.35, 0.0])

        self.start_cue(
            "prob_01",
            "大家好，概率小题最容易在符号细节上踩坑，来看这道正态分布方差题：设随机变量 X 服从 N(1, 4)，求 D(2X-3)。",
            "",
            tts_text="大家好，概率小题最容易在符号细节上踩坑，来看这道正态分布方差题：设随机变量 X 服从 N 1 4，求 D 2 X 减 3。",
        )
        self.play(FadeIn(stem), run_time=min(0.65, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("prob_01")

        self.start_cue(
            "prob_02",
            "四个选项分别是 A 为 5，B 为 8，C 为 13，D 为 16。",
            "",
            tts_text="四个选项分别是 A 为 5，B 为 8，C 为 13，D 为 16。",
        )
        highlight_clause(self, opts)
        self.end_cue("prob_02")

        # 选择题保留题干与四选项在顶区全程可见
        stem_top = stem.copy().scale(0.80)
        stem_top.move_to([max(bounds["stem_left_x"] + stem_top.width / 2.0, min(0.0, bounds["stem_right_x"] - stem_top.width / 2.0)), min(3.55, bounds["stem_top_y"]) - stem_top.height / 2.0, 0.0])

        theory = mixed_text(
            ("t", "核心知识点："),
            ("m", r"X \sim N(\mu, \sigma^2) \Rightarrow D(X)=\sigma^2"),
            ("t", "；且方差性质 "),
            ("m", r"D(aX + b) = a^2 D(X)"),
            font_size=25, color=HIGHLIGHT_BLUE,
        )
        warn_tip = aside_card(
            "易错警示：别看错方差和一次系数",
            [("t", "1. "), ("m", r"N(1, 4)"), ("t", " 中第二个参数 "), ("m", r"4"), ("t", " 本身就是方差而非标准差；"), ("m", r"a"), ("t", " 要平方而常数 "), ("m", r"-3"), ("t", " 方差为 0。")],
            kind="warning",
            width=11.0,
            title_size=23,
            body_size=21,
            pad_y=0.16,
        )
        calc1 = MathTex(r"D(X) = \sigma^2 = 4", color=INK_BLACK).scale(0.72)
        calc2 = MathTex(r"D(2X - 3) = 2^2 D(X) = 4 \times 4 = 16", color=INK_BLACK).scale(0.72)
        work = VGroup(theory, calc1, calc2).arrange(DOWN, aligned_edge=LEFT, buff=0.34)
        work.next_to(stem_top, DOWN, buff=0.40).set_x(0.0)
        warn_tip.next_to(work, DOWN, buff=0.28).set_x(0.0)

        self.start_cue(
            "prob_03",
            "先明确两个关键知识点，同时避开两个常见坑：第一，正态分布记号第二项 4 直接就是方差 σ^2，不要当成标准差；第二，线性变换方差 D(aX+b) = a^2 D(X)，常数 -3 消去、系数 2 必须平方。",
            "",
            pause_before_seconds=0.45,
            tts_text="先明确两个关键知识点，同时避开两个常见坑：第一，正态分布记号第二项 4 直接就是方差 sigma 平方，不要当成标准差；第二，线性变换方差 D a X 加 b 等于 a 平方 D X，常数负 3 消去、系数 2 必须平方。",
        )
        self.play(Transform(stem, stem_top), run_time=min(0.45, max(0.1, self.cue_time_left() * 0.20)))
        self.play(Write(VGroup(theory, calc1)), FadeIn(warn_tip), run_time=min(0.95, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("prob_03")

        self.start_cue(
            "prob_04",
            "把系数 2 平方变成 4，乘以方差 4 等于 16，所以本题选 D。",
            "",
            tts_text="把系数 2 平方变成 4，乘以方差 4 等于 16，所以本题选 D。",
        )
        self.play(FadeOut(warn_tip), Write(calc2), run_time=min(0.75, max(0.1, self.cue_time_left() * 0.45)))
        box = SurroundingRectangle(calc2, color=HIGHLIGHT_BLUE, buff=0.10)
        self.play(Create(box), stem[1][3].animate.set_color(HIGHLIGHT_BLUE), run_time=min(0.35, max(0.05, self.cue_time_left() * 0.30)))
        self.end_cue("prob_04")

        summary = aside_card(
            "方法与注意点总结",
            [("t", "1. 记号辨析：正态分布 "), ("m", r"N(\mu,\sigma^2)"), ("t", " 括号内第二个数直接是方差而非标准差。")],
            [("t", "2. 核心性质："), ("m", r"D(aX+b)=a^2 D(X)"), ("t", "，注意一次系数需平方、常数 "), ("m", r"b"), ("t", " 消去。")],
            [("t", "3. 易错警示：切勿写成 "), ("m", r"2D(X)"), ("t", " 或忘记去掉常数 "), ("m", r"-3"), ("t", "。")],
            kind="summary",
            width=11.4,
            title_size=26,
            body_size=24,
            line_buff=0.22,
        )
        summary.next_to(stem, DOWN, buff=0.42).set_x(0.0)

        self.start_cue(
            "prob_05",
            "最后小结两点易错点：第一，正态括号里第二位就是方差不是标准差；第二，求方差时常数消除且系数必须平方。",
            "",
            pause_before_seconds=0.45,
            tts_text="最后小结两点易错点：第一，正态括号里第二位就是方差不是标准差；第二，求方差时常数消除且系数必须平方。",
        )
        self.play(FadeOut(VGroup(work, box)), stem[1][3].animate.set_color(INK_BLACK), run_time=min(0.28, max(0.05, self.cue_time_left() * 0.15)))
        self.play(FadeIn(summary), run_time=min(0.70, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("prob_05")
```
