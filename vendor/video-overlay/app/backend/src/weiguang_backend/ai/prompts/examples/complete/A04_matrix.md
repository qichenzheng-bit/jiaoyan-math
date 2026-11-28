### 示例二：线性代数计算题（全宽 `matrix_chain` · 严守初等行变换）

```python title=scene_02
from manim import *
from animation_engine.code.authored_scene import AuthoredScene
from animation_engine.code.board_kit import (
    HIGHLIGHT_BLUE, INK_BLACK, aside_card,
    board_bounds, highlight_clause, matrix_chain, mixed_text,
)


class MatrixRankExample(AuthoredScene):
    def construct(self):
        self.camera.background_color = "#FFFFFF"
        bounds = board_bounds()
        stem = VGroup(
            mixed_text(("t", "求矩阵 "), ("m", r"A=\begin{pmatrix}1&2&1\\2&4&3\\3&6&4\end{pmatrix}"), ("t", " 的秩。"), font_size=28, color=INK_BLACK),
        ).move_to([0.0, 0.35, 0.0])

        self.start_cue(
            "alg_01",
            "同学们好，求具体矩阵的秩先别急着硬算行列式，先来看这道三阶矩阵 A 的已知元素。",
            "",
            tts_text="同学们好，求具体矩阵的秩先别急着硬算行列式，先来看这道三阶矩阵 A 的已知元素。",
        )
        self.play(FadeIn(stem), run_time=min(0.65, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("alg_01")

        self.start_cue(
            "alg_02",
            "矩阵元素全为整数，求秩最稳妥的办法是只做初等行变换化为行阶梯形。",
            "",
            tts_text="矩阵元素全为整数，求秩最稳妥的办法是只做初等行变换化为行阶梯形。",
        )
        highlight_clause(self, stem[0])
        self.end_cue("alg_02")

        stem_top = stem.copy().scale(0.80)
        stem_top.move_to([max(bounds["stem_left_x"] + stem_top.width / 2.0, min(0.0, bounds["stem_right_x"] - stem_top.width / 2.0)), min(3.55, bounds["stem_top_y"]) - stem_top.height / 2.0, 0.0])

        rule_tip = mixed_text(
            ("t", "核心知识点：初等行变换不改变矩阵的秩；注意"),
            ("m", r"r_2 - 2r_1"), ("t", "，"), ("m", r"r_3 - 3r_1"),
            ("t", " 时严禁混用列变换。"),
            font_size=24, color=HIGHLIGHT_BLUE,
        )
        chain = matrix_chain(
            [
                r"\begin{pmatrix}1&2&1\\2&4&3\\3&6&4\end{pmatrix}",
                r"\begin{pmatrix}1&2&1\\0&0&1\\0&0&1\end{pmatrix}",
                r"\begin{pmatrix}1&2&1\\0&0&1\\0&0&0\end{pmatrix}",
            ],
            [r"r_2-2r_1,\,r_3-3r_1", r"r_3-r_2"],
            max_width=12.4,
            scale=0.68,
        )
        rank_res = MathTex(r"r(A) = 2", color=INK_BLACK).scale(0.78)
        work = VGroup(rule_tip, chain, rank_res).arrange(DOWN, aligned_edge=LEFT, buff=0.38)
        work.next_to(stem_top, DOWN, buff=0.40).set_x(0.0)

        self.start_cue(
            "alg_03",
            "首先牢记知识点：初等变换不改变矩阵的秩，习惯上全过程只做初等行变换。我们先用第二行减 2 倍第一行，第三行减 3 倍第一行。",
            "",
            pause_before_seconds=0.45,
            tts_text="首先牢记知识点：初等变换不改变矩阵的秩，习惯上全过程只做初等行变换。我们先用第二行减 2 倍第一行，第三行减 3 倍第一行。",
        )
        self.play(Transform(stem, stem_top), run_time=min(0.45, max(0.1, self.cue_time_left() * 0.25)))
        self.play(Write(rule_tip), Write(chain), run_time=min(1.0, max(0.1, self.cue_time_left() * 0.55)))
        self.end_cue("alg_03")

        self.start_cue(
            "alg_04",
            "接着用第三行减去第二行，第三行全部清零。此时行阶梯形恰有两个非零行，因此矩阵 A 的秩 r(A) 等于 2。",
            "",
            tts_text="接着用第三行减去第二行，第三行全部清零。此时行阶梯形恰有两个非零行，因此矩阵 A 的秩 r A 等于 2。",
        )
        self.play(Write(rank_res), run_time=min(0.65, max(0.1, self.cue_time_left() * 0.45)))
        box = SurroundingRectangle(rank_res, color=HIGHLIGHT_BLUE, buff=0.10)
        self.play(Create(box), run_time=min(0.30, max(0.05, self.cue_time_left() * 0.25)))
        self.end_cue("alg_04")

        summary = aside_card(
            "方法与注意点总结",
            [("t", "1. 通法：求具体矩阵的秩优先化为行阶梯形，数非零行行数。")],
            [("t", "2. 规范书写：箭头上方写清行变换记号（如 "), ("m", r"r_3-r_2"), ("t", "），禁用等号连写。")],
            [("t", "3. 易错警示：若解线性方程组，切忌行变换与列变换混用破坏解集。")],
            kind="summary",
            width=11.4,
            title_size=26,
            body_size=24,
            line_buff=0.22,
        )
        summary.next_to(stem, DOWN, buff=0.45).set_x(0.0)

        self.start_cue(
            "alg_05",
            "最后回顾要点：求矩阵秩找非零行最直观；矩阵间用行等价箭头并标清倍加记号，千万不能写成等号。",
            "",
            pause_before_seconds=0.45,
            tts_text="最后回顾要点：求矩阵秩找非零行最直观；矩阵间用行等价箭头并标清倍加记号，千万不能写成等号。",
        )
        self.play(FadeOut(VGroup(work, box)), run_time=min(0.28, max(0.05, self.cue_time_left() * 0.15)))
        self.play(FadeIn(summary), run_time=min(0.70, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("alg_05")
```
