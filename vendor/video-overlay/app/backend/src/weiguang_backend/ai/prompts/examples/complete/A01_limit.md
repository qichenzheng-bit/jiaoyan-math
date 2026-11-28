### 示例一：高等数学计算题（全宽居中板书 · 自主排版与大字号分条总结）

```python title=scene_01
from manim import *
from animation_engine.code.authored_scene import AuthoredScene
from animation_engine.code.board_kit import (
    HIGHLIGHT_BLUE, INK_BLACK, INK_DARK, aside_card,
    board_bounds, board_note, fit_stem, highlight_clause, mixed_text,
)


class CalcExample(AuthoredScene):
    def construct(self):
        self.camera.background_color = "#FFFFFF"
        bounds = board_bounds()

        # 开场：大字号居中展示完整题干
        part_a = mixed_text(("t", "求不定积分 "), ("m", r"\int x e^{-x}\,\mathrm{d}x"), ("t", "。"), font_size=28, color=INK_BLACK)
        stem_center = VGroup(part_a).move_to([0.0, 0.35, 0.0])

        self.start_cue(
            "calc_01",
            "同学们好，遇到两个不同函数相乘求积分，先来看今天这道题：求 ∫ x e^(-x) dx。",
            "",
            tts_text="同学们好，遇到两个不同函数相乘求积分，先来看今天这道题：求积分 x 乘 e 的负 x 次方 d x。",
        )
        self.play(FadeIn(stem_center), run_time=min(0.65, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("calc_01")

        self.start_cue(
            "calc_02",
            "被积函数由幂函数 x 和指数函数 e^(-x) 相乘构成。",
            "",
            tts_text="被积函数由幂函数 x 和指数函数 e 的负 x 次方相乘构成。",
        )
        highlight_clause(self, part_a[1])
        self.end_cue("calc_02")

        # 进入讲解：调用 fit_stem 默认视觉居中并自动避让右上水印
        stem_top = stem_center.copy().scale(0.84)
        fit_stem(stem_top, bounds)

        # 思维引导：先排除错路，再结合简短路线式；用轻量 board_note 节省高度，下方接着写第一步
        guide_note = board_note(
            [("t", "弯路排除：若把 "), ("m", r"x\,\mathrm{d}x"), ("t", " 凑成 "), ("m", r"\frac{1}{2}\mathrm{d}(x^2)"), ("t", "，次数越积越高，越算越乱。")],
            [("t", "突破路线："), ("m", r"x'\!=\!1"), ("t", "（降次消 "), ("m", r"x"), ("t", "），把 "), ("m", r"e^{-x}\mathrm{d}x=-\mathrm{d}(e^{-x})"), ("t", " 凑入微分号。")],
            color="#6D28D9",
            font_size=22,
        )
        guide_note.next_to(stem_top, DOWN, buff=0.34).set_x(0.0)

        self.start_cue(
            "calc_03",
            "动手前先避个弯路：要是把 x 凑进微分号会升成 x 平方，反而更麻烦。怎么办？——反过来让 x 求导降成 1，把 e^(-x) 凑进微分号！",
            "",
            pause_before_seconds=0.45,
            tts_text="动手前先避个弯路：要是把 x 凑进微分号会升成 x 平方，反而更麻烦。怎么办？反过来让 x 求导降成 1，把 e 的负 x 次方凑进微分号！",
        )
        self.play(Transform(stem_center, stem_top), run_time=min(0.45, max(0.1, self.cue_time_left() * 0.25)))
        self.play(FadeIn(guide_note), run_time=min(0.75, max(0.1, self.cue_time_left() * 0.40)))
        self.end_cue("calc_03")

        # 引导下方空位充足：不提前清屏，直接下方写出公式与第 1 步
        kp_line = mixed_text(
            ("t", "分部积分公式（"), ("m", r"u,v"), ("t", " 连续可导）："),
            ("m", r"\int u\,\mathrm{d}v = uv - \int v\,\mathrm{d}u"),
            font_size=25, color=HIGHLIGHT_BLUE,
        )
        step1 = MathTex(r"\int x e^{-x}\,\mathrm{d}x = -\int x\,\mathrm{d}(e^{-x})", color=INK_BLACK).scale(0.72)
        step1_below = VGroup(kp_line, step1).arrange(DOWN, aligned_edge=LEFT, buff=0.28)
        step1_below.next_to(guide_note, DOWN, buff=0.36).set_x(0.0)

        step2 = MathTex(r"= -x e^{-x} + \int e^{-x}\,\mathrm{d}x", color=INK_BLACK).scale(0.72)
        step3 = MathTex(r"= -x e^{-x} - e^{-x} + C", color=INK_BLACK).scale(0.72)
        target_board = VGroup(kp_line.copy(), step1.copy(), step2, step3).arrange(DOWN, aligned_edge=LEFT, buff=0.32)
        target_board.next_to(stem_top, DOWN, buff=0.36).set_x(0.0)

        self.start_cue(
            "calc_04",
            "套用分部积分公式 ∫ u dv = uv - ∫ v du，条件是 u 和 v 连续可导。第一步先把 e^(-x) dx 凑成 -d(e^(-x))。",
            "",
            pause_before_seconds=0.40,
            tts_text="套用分部积分公式积分 u d v 等于 u v 减积分 v d u，条件是 u 和 v 连续可导。第一步先把 e 的负 x 次方 d x 凑成负 d e 的负 x 次方。",
        )
        self.play(Write(step1_below), run_time=min(0.95, max(0.1, self.cue_time_left() * 0.50)))
        self.end_cue("calc_04")

        # 轻量红线批注提醒双重负号与 +C，同时局部上划线标出 + 号
        warn_note = board_note(
            [("t", "易错提醒：公式减号与负号相抵变成 "), ("m", r"+"), ("t", "；结尾千万别忘 "), ("m", r"+C"), ("t", "。")],
            color="#B91C1C",
            font_size=22,
        )
        warn_note.next_to(target_board[2], DOWN, buff=0.26).set_x(0.0)

        self.start_cue(
            "calc_05",
            "接着按公式展开得到 -x e^(-x)，注意这里符号是正还是负？——双重负号抵消，变成加号！",
            "",
            tts_text="接着按公式展开得到负 x e 的负 x 次方，注意这里符号是正还是负？双重负号抵消，变成加号！",
        )
        self.play(
            FadeOut(guide_note),
            step1_below.animate.move_to(VGroup(target_board[0], target_board[1])),
            run_time=min(0.45, max(0.1, self.cue_time_left() * 0.22)),
        )
        self.play(Write(step2), run_time=min(0.65, max(0.1, self.cue_time_left() * 0.30)))
        self.play(FadeIn(warn_note), run_time=min(0.45, max(0.05, self.cue_time_left() * 0.22)))
        self.end_cue("calc_05")

        self.start_cue(
            "calc_06",
            "再求一次原函数得到 -e^(-x)，补上常数 C，并求导口算回验，正好还原 x e^(-x)，答案稳稳锁定。",
            "",
            pause_before_seconds=0.35,
            tts_text="再求一次原函数得到负 e 的负 x 次方，补上常数 C，并求导口算回验，正好还原 x 乘 e 的负 x 次方，答案稳稳锁定。",
        )
        self.play(FadeOut(warn_note), run_time=min(0.24, max(0.05, self.cue_time_left() * 0.14)))
        self.play(Write(step3), run_time=min(0.75, max(0.1, self.cue_time_left() * 0.42)))
        ans_box = SurroundingRectangle(step3, color=HIGHLIGHT_BLUE, buff=0.10)
        self.play(Create(ans_box), run_time=min(0.32, max(0.05, self.cue_time_left() * 0.22)))
        self.check_layout("定格答案", question=stem_center, working=VGroup(step1_below, step2, step3, ans_box))
        self.end_cue("calc_06")

        # 总结环节：清晰卡片展示通法 + 考场变式迁移
        summary = aside_card(
            "方法与注意点总结",
            [("t", "1. 题型特征：幂函数与指数/三角函数乘积积分，优先考虑分部积分。")],
            [("t", "2. 通用口诀：反对幂指三，把靠后一类（如 "), ("m", r"e^{-x}"), ("t", "）凑进 "), ("m", r"\mathrm{d}v"), ("t", " 避免升次。")],
            [("t", "3. 易错与变式：双重变号别丢符号，结果补 "), ("m", r"+C"), ("t", "；若换成 "), ("m", r"x^2 e^{-x}"), ("t", " 连用两次同法即可。")],
            kind="summary",
            width=11.4,
            title_size=26,
            body_size=23,
            line_buff=0.22,
        )
        summary.next_to(stem_center, DOWN, buff=0.42).set_x(0.0)

        self.start_cue(
            "calc_07",
            "最后我们记住三点核心规律：按反对幂指三把指数凑进微分号；小心双重负号与常数 C；考场遇到 x 平方乘 e^(-x)，同样按这套方法连续用两次就行。",
            "",
            pause_before_seconds=0.50,
            tts_text="最后我们记住三点核心规律：按反对幂指三把指数凑进微分号；小心双重负号与常数 C；考场遇到 x 平方乘 e 的负 x 次方，同样按这套方法连续用两次就行。",
        )
        self.play(FadeOut(VGroup(step1_below, step2, step3, ans_box)), run_time=min(0.28, max(0.05, self.cue_time_left() * 0.15)))
        self.play(FadeIn(summary), run_time=min(0.75, max(0.1, self.cue_time_left() * 0.40)))
        self.check_layout("方法总结", question=stem_center, pedagogy=summary)
        self.end_cue("calc_07")
```
