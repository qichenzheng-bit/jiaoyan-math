### 示例五：真题级两小问跨幕衔接（`fit_stem` 居中避让 + 小问切换保留结论）

```python title=scene_05
from manim import *
from animation_engine.code.authored_scene import AuthoredScene
from animation_engine.code.board_kit import (
    HIGHLIGHT_BLUE, INK_BLACK, board_bounds, board_note,
    fit_stem, highlight_clause, mixed_text,
)


class MeanValueScene01(AuthoredScene):
    def construct(self):
        self.camera.background_color = "#FFFFFF"
        bounds = board_bounds()

        l1 = mixed_text(("t", "设可导函数 "), ("m", r"f(x)"), ("t", " 严格单调递增，且 "), ("m", r"\int_{-1}^{1}f(x)\,\mathrm{d}x=0"), ("t", "，设 "), ("m", r"a=\int_{0}^{1}f(x)\,\mathrm{d}x"), ("t", "。"), font_size=26, color=INK_BLACK)
        l2 = mixed_text(("m", r"(1)"), ("t", " 证明："), ("m", r"a>0"), ("t", "；"), font_size=26, color=INK_BLACK)
        l3 = mixed_text(("m", r"(2)"), ("t", " 若 "), ("m", r"F(x)=a(1-x^2)+\int_{1}^{x}f(t)\,\mathrm{d}t"), ("t", "，证明存在 "), ("m", r"\xi\in(-1,1)"), ("t", " 使得 "), ("m", r"F''(\xi)=0"), ("t", "。"), font_size=26, color=INK_BLACK)
        full_stem = VGroup(l1, l2, l3).arrange(DOWN, aligned_edge=LEFT, buff=0.20).move_to([0.0, 0.35, 0.0])

        self.start_cue(
            "mv_01",
            "同学们，证明大题往往第一问就是第二问的铺垫，我们先来看清这道积分与中值定理结合的真题。",
            "",
            tts_text="同学们，证明大题往往第一问就是第二问的铺垫，我们先来看清这道积分与中值定理结合的真题。",
        )
        self.play(FadeIn(full_stem), run_time=min(0.65, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("mv_01")

        self.start_cue(
            "mv_02",
            "已知可导函数 f(x) 严格单调递增，从 -1 积到 1 等于 0，记 a 为 0 到 1 的积分；第一问要证 a 大于 0，第二问要证存在 ξ 使得 F''(ξ)=0。",
            "",
            tts_text="已知可导函数 f x 严格单调递增，从负 1 积到 1 等于 0，记 a 为 0 到 1 的积分；第一问要证 a 大于 0，第二问要证存在 ξ 使得 F 两撇 ξ 等于 0。",
        )
        highlight_clause(self, l1, l2, l3)
        self.end_cue("mv_02")

        # 讲第 (1) 小问时顶部仅聚焦「主题干 + 第 (1) 小问」，保持视觉居中
        stem_p1 = VGroup(l1.copy(), l2.copy()).arrange(DOWN, aligned_edge=LEFT, buff=0.14).scale(0.82)
        fit_stem(stem_p1, bounds, max_height=1.50)

        guide1 = board_note(
            [("t", "突破口：把 "), ("m", r"\int_{-1}^{1}f(x)\,\mathrm{d}x=0"), ("t", " 从 "), ("m", r"0"), ("t", " 拆成对称两段，利用 "), ("m", r"f(-x)<f(x)\ (x>0)"), ("t", " 比较大小。")],
            color="#6D28D9",
            font_size=22,
        )
        guide1.next_to(stem_p1, DOWN, buff=0.34).set_x(0.0)

        p1_s1 = MathTex(r"\int_{-1}^{0}f(x)\,\mathrm{d}x + \int_{0}^{1}f(x)\,\mathrm{d}x = 0", color=INK_BLACK).scale(0.72)
        p1_s2 = mixed_text(("t", "当 "), ("m", r"t\in(0,1]"), ("t", " 时，"), ("m", r"-t<t\Rightarrow f(-t)<f(t)"), ("t", "，故 "), ("m", r"\int_{-1}^{0}f(x)\,\mathrm{d}x = \int_{0}^{1}f(-t)\,\mathrm{d}t < \int_{0}^{1}f(t)\,\mathrm{d}t = a"), font_size=24, color=INK_BLACK)
        p1_s3 = MathTex(r"\Longrightarrow -a < a \Longrightarrow 2a > 0 \Longrightarrow a > 0", color=INK_BLACK).scale(0.74)
        proof1 = VGroup(p1_s1, p1_s2, p1_s3).arrange(DOWN, aligned_edge=LEFT, buff=0.30)
        proof1.next_to(guide1, DOWN, buff=0.34).set_x(0.0)

        self.start_cue(
            "mv_03",
            "先来看第 (1) 问：怎么证 a 大于 0？——把 -1 到 1 拆成 -1 到 0 加 0 到 1，再借助严格单调递增比一比两边大小就行。",
            "",
            pause_before_seconds=0.45,
            tts_text="先来看第 1 问：怎么证 a 大于 0？把负 1 到 1 拆成负 1 到 0 加 0 到 1，再借助严格单调递增比一比两边大小就行。",
        )
        self.play(FadeOut(l3), Transform(VGroup(l1, l2), stem_p1), run_time=min(0.45, max(0.1, self.cue_time_left() * 0.25)))
        self.play(FadeIn(guide1), run_time=min(0.65, max(0.1, self.cue_time_left() * 0.35)))
        self.end_cue("mv_03")

        self.start_cue(
            "mv_04",
            "把积分区间从零拆成两段：当 t 大于 0 时 -t 小于 t，由严格递增有 f(-t) 小于 f(t)，因此左半段积分小于 a，也就是 -a 小于 a，立刻证出 a 大于 0。",
            "",
            tts_text="把积分区间从零拆成两段：当 t 大于 0 时负 t 小于 t，由严格递增有 f 负 t 小于 f t，因此左半段积分小于 a，也就是负 a 小于 a，立刻证出 a 大于 0。",
        )
        self.play(Write(proof1), run_time=min(1.0, max(0.1, self.cue_time_left() * 0.55)))
        p1_box = SurroundingRectangle(p1_s3, color=HIGHLIGHT_BLUE, buff=0.08)
        self.play(Create(p1_box), run_time=min(0.32, max(0.05, self.cue_time_left() * 0.22)))
        self.end_cue("mv_04")
```

```python title=scene_06
from manim import *
from animation_engine.code.authored_scene import AuthoredScene
from animation_engine.code.board_kit import (
    HIGHLIGHT_BLUE, INK_BLACK, aside_card, board_bounds,
    board_note, fit_stem, mixed_text,
)


class MeanValueScene02(AuthoredScene):
    def construct(self):
        self.camera.background_color = "#FFFFFF"
        bounds = board_bounds()

        # 切幕进入第 (2) 问：顶部聚焦「主题干 + 第 (2) 小问」，并显式保留第 (1) 问已证结论
        l1 = mixed_text(("t", "设可导函数 "), ("m", r"f(x)"), ("t", " 严格单调递增，且 "), ("m", r"\int_{-1}^{1}f(x)\,\mathrm{d}x=0"), ("t", "，设 "), ("m", r"a=\int_{0}^{1}f(x)\,\mathrm{d}x"), ("t", "。"), font_size=26, color=INK_BLACK)
        l3 = mixed_text(("m", r"(2)"), ("t", " 若 "), ("m", r"F(x)=a(1-x^2)+\int_{1}^{x}f(t)\,\mathrm{d}t"), ("t", "，证明存在 "), ("m", r"\xi\in(-1,1)"), ("t", " 使得 "), ("m", r"F''(\xi)=0"), ("t", "。"), font_size=26, color=INK_BLACK)
        stem_p2 = VGroup(l1, l3).arrange(DOWN, aligned_edge=LEFT, buff=0.14).scale(0.82)
        fit_stem(stem_p2, bounds, max_height=1.50)

        kept_p1 = mixed_text(("t", "第(1)问已证："), ("m", r"a>0"), font_size=23, color=HIGHLIGHT_BLUE)
        kept_p1.next_to(stem_p2, DOWN, buff=0.22).set_x(0.0)
        self.add(stem_p2, kept_p1)

        s1 = MathTex(r"F(1)=0,\quad F(-1)=-\int_{-1}^{1}f(t)\,\mathrm{d}t=0,\quad F(0)=a-\int_{0}^{1}f(t)\,\mathrm{d}t=0", color=INK_BLACK).scale(0.70)
        warn_r = board_note(
            [("t", "易错提醒："), ("m", r"f"), ("t", " 可导保证 "), ("m", r"F"), ("t", " 在 "), ("m", r"[-1,1]"), ("t", " 二阶可导；两次罗尔必须凑齐 "), ("m", r"3"), ("t", " 个零点。")],
            color="#B91C1C",
            font_size=22,
        )
        s2 = mixed_text(("t", "对 "), ("m", r"F(x)"), ("t", " 在 "), ("m", r"[-1,0]"), ("t", " 与 "), ("m", r"[0,1]"), ("t", " 分别用罗尔定理，得 "), ("m", r"F'(\xi_1)=F'(\xi_2)=0\ (\xi_1<0<\xi_2)"), font_size=24, color=INK_BLACK)
        s3 = mixed_text(("t", "再对 "), ("m", r"F'(x)"), ("t", " 在 "), ("m", r"[\xi_1,\xi_2]"), ("t", " 用罗尔定理，即存在 "), ("m", r"\xi\in(-1,1)"), ("t", " 使 "), ("m", r"F''(\xi)=0"), font_size=24, color=INK_BLACK)
        proof2 = VGroup(s1, warn_r, s2, s3).arrange(DOWN, aligned_edge=LEFT, buff=0.30)
        proof2.next_to(kept_p1, DOWN, buff=0.34).set_x(0.0)

        self.start_cue(
            "mv_05",
            "拿到第 (1) 问证出的 a 大于 0，切入第 (2) 问。要证二阶导数有零点，先别硬求导凑函数，算一算端点和零点函数值：F(1)=0，F(-1)=0，再代入 F(0) 正好等于 a 减 a 也等于 0！",
            "",
            pause_before_seconds=0.45,
            tts_text="拿到第 1 问证出的 a 大于 0，切入第 2 问。要证二阶导数有零点，先别硬求导凑函数，算一算端点和零点函数值：F 1 等于 0，F 负 1 等于 0，再代入 F 0 正好等于 a 减 a 也等于 0！",
        )
        self.play(Write(s1), FadeIn(warn_r), run_time=min(0.95, max(0.1, self.cue_time_left() * 0.50)))
        self.end_cue("mv_05")

        self.start_cue(
            "mv_06",
            "三个零点齐了！先在 [-1, 0] 和 [0, 1] 各用一次罗尔定理得到一阶导数的两个零点 ξ_1、ξ_2，再对 F'(x) 用一次罗尔定理，马上证出 F''(ξ)=0。",
            "",
            tts_text="三个零点齐了！先在负 1 到 0 和 0 到 1 各用一次罗尔定理得到一阶导数的两个零点 ξ 一、ξ 二，再对 F 撇 x 用一次罗尔定理，马上证出 F 两撇 ξ 等于 0。",
        )
        self.play(Write(s2), run_time=min(0.75, max(0.1, self.cue_time_left() * 0.42)))
        self.play(Write(s3), run_time=min(0.75, max(0.1, self.cue_time_left() * 0.42)))
        self.end_cue("mv_06")

        summary = aside_card(
            "方法与注意点总结",
            [("t", "1. 问间衔接：两小问证明题第 (1) 问结论与记号常在第 (2) 问直接复用。")],
            [("t", "2. 高阶中值破局：见到 "), ("m", r"F''(\xi)=0"), ("t", " 优先找 "), ("m", r"3"), ("t", " 个相等函数值点连用两次罗尔定理。")],
            [("t", "3. 变式迁移：若给出 "), ("m", r"F''(\xi)+F(\xi)=0"), ("t", " 等线性组合，先乘积分因子再找零点。")],
            kind="summary",
            width=11.4,
            title_size=26,
            body_size=23,
            line_buff=0.22,
        )
        summary.next_to(stem_p2, DOWN, buff=0.45).set_x(0.0)

        self.start_cue(
            "mv_07",
            "最后总结：二阶导数中值命题通常靠找 3 个函数零点连用两次罗尔；如果是带加减组合的二阶导数，思路一样，先配出可导原函数再找零点。",
            "",
            pause_before_seconds=0.50,
            tts_text="最后总结：二阶导数中值命题通常靠找 3 个函数零点连用两次罗尔；如果是带加减组合的二阶导数，思路一样，先配出可导原函数再找零点。",
        )
        self.play(FadeOut(VGroup(kept_p1, proof2)), run_time=min(0.28, max(0.05, self.cue_time_left() * 0.15)))
        self.play(FadeIn(summary), run_time=min(0.72, max(0.1, self.cue_time_left() * 0.45)))
        self.end_cue("mv_07")
```
