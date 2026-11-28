"""AI 生成场景的可复用排版与考研板书轻量组件（白底深字，安全区内自适应）。

提供像素安全区换算、纯中文+LaTeX混排、轻量化旁注/知识/警示卡片、
双栏协同与安全区缩放定位，避免每节课重复手写大量样板几何代码。
"""
from __future__ import annotations

from manim import (
    Arrow,
    Axes,
    BackgroundRectangle,
    DOWN,
    LEFT,
    Line,
    RIGHT,
    UP,
    MathTex,
    Mobject,
    Rectangle,
    RoundedRectangle,
    Text,
    VGroup,
)

from ..core.video_settings import (
    CAPTION_BAND_TOP_PX,
    MANIM_FRAME_HEIGHT,
    PX_PER_UNIT,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from ..errors import EngineError
from ..infra.fonts import cjk_text_font_family

INK_BLACK = "#000000"
INK_DARK = "#111827"
INK_MUTED = "#374151"
HIGHLIGHT_BLUE = "#1D4ED8"
#: 保护手机端清晰可读性的最低缩放底线，禁止组件为凑空间把字号压成蚂蚁字。
MIN_READABLE_SCALE = 0.80

# 轻量辅助模块配色：浅背景 + 左侧主题色强调条 + 主题色标题 + 高对比深色正文。
CARD_THEMES: dict[str, dict[str, str]] = {
    "guide": {"accent": "#6D28D9", "bg": "#F5F3FF", "border": "#DDD6FE"},
    "knowledge": {"accent": "#1D4ED8", "bg": "#EFF6FF", "border": "#BFDBFE"},
    "warning": {"accent": "#B91C1C", "bg": "#FEF2F2", "border": "#FECACA"},
    "summary": {"accent": "#0F766E", "bg": "#F0FDFA", "border": "#99F6E4"},
}

_PUNCT_CHARS = frozenset("，。！？；：、,.!?;: ")


def _safe_font_family() -> str | None:
    try:
        return cjk_text_font_family()
    except EngineError:
        return None


def board_bounds(
    watermark_safe_region_px: dict | None = None,
    caption_safe_region_px: dict | None = None,
    *,
    frame_width: float | None = None,
    frame_height: float | None = None,
) -> dict[str, float]:
    """将像素安全区换算为 Manim 画布坐标，并按单侧避让计算顶部可用宽度。"""
    fw = float(frame_width or (VIDEO_WIDTH / PX_PER_UNIT))
    fh = float(frame_height or MANIM_FRAME_HEIGHT)
    half_w = fw / 2.0
    half_h = fh / 2.0

    def px_to_x(px: float) -> float:
        return (float(px) - VIDEO_WIDTH / 2.0) / PX_PER_UNIT

    def py_to_y(py: float) -> float:
        return (VIDEO_HEIGHT / 2.0 - float(py)) / PX_PER_UNIT

    left_x = -half_w + 0.45
    right_x = half_w - 0.45
    stem_left_x = left_x
    stem_right_x = right_x
    stem_top_y = half_h - 0.35

    if isinstance(watermark_safe_region_px, dict) and isinstance(
        watermark_safe_region_px.get("rect"), dict
    ):
        rect = watermark_safe_region_px["rect"]
        gap = float(watermark_safe_region_px.get("clearance_px") or 16)
        wm_left_x = px_to_x(float(rect["x"]) - gap)
        wm_right_x = px_to_x(float(rect["x"]) + float(rect["width"]) + gap)
        wm_center_x = (wm_left_x + wm_right_x) / 2.0
        # 仅在水印所在侧做单侧避让，绝不做双边对称扣减浪费左侧空间。
        if wm_center_x >= 0:
            stem_right_x = min(right_x, wm_left_x - 0.16)
        else:
            stem_left_x = max(left_x, wm_right_x + 0.16)

    cap_top_px = float(CAPTION_BAND_TOP_PX)
    if isinstance(caption_safe_region_px, dict) and isinstance(
        caption_safe_region_px.get("rect"), dict
    ):
        cap_top_px = float(caption_safe_region_px["rect"].get("y", cap_top_px))

    caption_top_y = py_to_y(cap_top_px)
    board_floor_y = caption_top_y + 0.18
    return {
        "left_x": round(left_x, 3),
        "right_x": round(right_x, 3),
        "stem_top_y": round(stem_top_y, 3),
        "stem_left_x": round(stem_left_x, 3),
        "stem_right_x": round(stem_right_x, 3),
        "stem_width": round(max(0.0, stem_right_x - stem_left_x), 3),
        "caption_top_y": round(caption_top_y, 3),
        "board_floor_y": round(board_floor_y, 3),
        "board_width": round(right_x - left_x, 3),
    }


def mixed_text(
    *parts,
    font_size: float = 26,
    math_scale: float | None = None,
    color: str = INK_BLACK,
    buff: float | None = None,
) -> VGroup:
    """将纯中文 Text 与纯 ASCII MathTex 片段按统一字高与基线横排拼接（可选辅助工具）。

    支持 ``\\min_{...}`` / ``\\sum_{...}`` 等正下方下标公式的自动主干对齐，
    避免正下方下标把前面的中文标签拉偏。
    """
    family = _safe_font_family()
    ratio = font_size / 26.0
    scale = float(math_scale if math_scale is not None else 0.72 * ratio)
    gap = float(buff if buff is not None else 0.08 * ratio)
    punct_gap = 0.025 * ratio
    objs: list[Mobject] = []
    math_sources: list[str | None] = []
    punct_flags: list[bool] = []
    text_kwargs = {"font": family} if family else {}

    for item in parts:
        if isinstance(item, Mobject):
            objs.append(item)
            math_sources.append(None)
            punct_flags.append(False)
            continue
        if isinstance(item, str):
            kind, val = "t", item
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            kind, val = str(item[0]), str(item[1])
        else:
            continue
        if not val.strip():
            continue
        if kind in ("m", "math"):
            objs.append(MathTex(val, color=color).scale(scale))
            math_sources.append(val.strip())
            punct_flags.append(False)
        else:
            objs.append(Text(val, color=color, font_size=font_size, **text_kwargs))
            math_sources.append(None)
            punct_flags.append(all(ch in _PUNCT_CHARS for ch in val))

    if not objs:
        return VGroup()
    if len(objs) == 1:
        return objs[0] if isinstance(objs[0], VGroup) else VGroup(objs[0])

    # 以首个纯中文 Text（或首对象）为中心基准，逐项水平排布；
    # 若公式以字母/括号开头且内部带正下方下标（如 T = \min_{1<=i<=n} X_i），
    # 按其首字形主干中心对齐，确保下标留在正下方且不拉歪中文基线。
    anchor_ref = next(
        (o for o, is_p, ms in zip(objs, punct_flags, math_sources)
         if ms is None and not is_p and isinstance(o, Text)),
        objs[0],
    )
    base_y = anchor_ref.get_center()[1]

    def _align_item(obj: Mobject, raw_tex: str | None) -> None:
        if raw_tex and raw_tex[0].isalpha():
            try:
                glyph_y = obj[0][0].get_center()[1]
                obj.shift([0.0, base_y - glyph_y, 0.0])
                return
            except (IndexError, TypeError):
                pass
        obj.set_y(base_y)

    _align_item(objs[0], math_sources[0])
    prev = objs[0]
    for cur, is_punct, raw_tex in zip(objs[1:], punct_flags[1:], math_sources[1:]):
        cur.next_to(prev, RIGHT, buff=punct_gap if is_punct else gap)
        _align_item(cur, raw_tex)
        prev = cur
    group = VGroup(*objs)
    if any(punct_flags):
        ref = next(
            (o for o, is_p in zip(objs, punct_flags) if not is_p and isinstance(o, Text)),
            None,
        )
        if ref is None:
            ref = Text("国", color=color, font_size=font_size, **text_kwargs)
            ref.set_y(base_y)
        ref_bottom = ref.get_bottom()[1]
        for o, is_p in zip(objs, punct_flags):
            if is_p:
                o.set_y(ref_bottom + o.height * 0.5 + 0.02 * ratio)
    return group


def _normalize_card_line(line, *, body_size: float) -> Mobject:
    if isinstance(line, Mobject):
        return line
    if isinstance(line, str):
        return mixed_text(("t", line), font_size=body_size, color=INK_DARK)
    if isinstance(line, (list, tuple)):
        return mixed_text(*line, font_size=body_size, color=INK_DARK)
    return mixed_text(("t", str(line)), font_size=body_size, color=INK_DARK)


def aside_card(
    title: str,
    *body_lines,
    kind: str = "knowledge",
    width: float = 5.0,
    title_size: float = 28,
    body_size: float = 26,
    line_buff: float = 0.20,
    pad_x: float = 0.24,
    pad_y: float = 0.22,
    min_scale: float = MIN_READABLE_SCALE,
) -> VGroup:
    """可选辅助卡片组件（浅底 + 左侧主题色强调条 + 深色正文，不强制缩放牺牲可读性）。"""
    palette = CARD_THEMES.get(kind, CARD_THEMES["knowledge"])
    family = _safe_font_family()
    text_kwargs = {"font": family} if family else {}

    header = Text(
        title,
        color=palette["accent"],
        font_size=title_size,
        weight="BOLD",
        **text_kwargs,
    )
    rows: list[Mobject] = [header]
    for item in body_lines:
        row = _normalize_card_line(item, body_size=body_size)
        if len(row) > 0 or not isinstance(row, VGroup):
            rows.append(row)

    inner = VGroup(*rows).arrange(DOWN, aligned_edge=LEFT, buff=line_buff)
    max_inner_w = max(1.5, width - 2 * pad_x - 0.12)
    floor = max(MIN_READABLE_SCALE, float(min_scale))
    if inner.width > max_inner_w:
        # 禁止无下限整体缩放：最多缩放到 min_scale，更长内容应由调用方合理分行
        inner.scale(max(floor, max_inner_w / inner.width))

    box_w = max(width, inner.width + 2 * pad_x + 0.30)
    box_h = inner.height + 2 * pad_y
    bg = RoundedRectangle(
        width=box_w,
        height=box_h,
        corner_radius=0.10,
        fill_color=palette["bg"],
        fill_opacity=0.96,
        stroke_color=palette["border"],
        stroke_width=1.4,
    )
    accent_bar = Rectangle(
        width=0.075,
        height=max(0.2, box_h - 0.14),
        fill_color=palette["accent"],
        fill_opacity=1.0,
        stroke_width=0,
    )
    accent_bar.next_to(bg.get_left(), RIGHT, buff=0.05)
    inner.next_to(accent_bar, RIGHT, buff=0.18)
    inner.set_y(bg.get_center()[1])
    card = VGroup(bg, accent_bar, inner)
    card._wg_card = True  # type: ignore[attr-defined]
    return card


def _layout_floor(obj: Mobject, min_scale: float) -> float:
    """Track cumulative helper scaling; never silently squeeze below 80%."""
    applied = float(getattr(obj, "_wg_layout_scale", 1.0))
    return min(1.0, max(MIN_READABLE_SCALE, float(min_scale)) / max(applied, 1e-8))


def _layout_scale(obj: Mobject, factor: float) -> None:
    if factor < 1.0:
        obj.scale(factor)
        obj._wg_layout_scale = float(getattr(obj, "_wg_layout_scale", 1.0)) * factor


def fit_into_region(
    group: Mobject,
    *,
    top_y: float,
    bottom_y: float,
    left_x: float | None = None,
    right_x: float | None = None,
    center_x: float | None = 0.0,
    align_left: bool = False,
    align_top: bool = False,
    min_scale: float = MIN_READABLE_SCALE,
) -> Mobject:
    """可选安全区定位工具：在可读缩放底线内微调，禁止为硬塞区域无下限压缩字体。"""
    max_h = max(0.35, float(top_y) - float(bottom_y))
    scale = 1.0
    if group.height > max_h:
        scale = min(scale, max_h / group.height)
    if left_x is not None and right_x is not None:
        max_w = max(0.5, float(right_x) - float(left_x))
        if group.width * scale > max_w:
            scale = min(scale, max_w / group.width)
    floor = _layout_floor(group, min_scale)
    if scale + 1e-8 < floor:
        raise EngineError("LAYOUT_REGION_TOO_SMALL: 请调整换行、布局或切幕，不得继续压缩字号")
    _layout_scale(group, scale)

    if align_left and left_x is not None:
        target_x = float(left_x) + group.width / 2.0
    elif center_x is not None:
        target_x = float(center_x)
    elif left_x is not None and right_x is not None:
        target_x = (float(left_x) + float(right_x)) / 2.0
    else:
        target_x = group.get_center()[0]

    if align_top:
        target_y = float(top_y) - group.height / 2.0
    else:
        target_y = (float(top_y) + float(bottom_y)) / 2.0

    if left_x is not None and right_x is not None:
        target_x = max(float(left_x) + group.width / 2.0, min(target_x, float(right_x) - group.width / 2.0))
    group.move_to([target_x, target_y, 0.0])
    return group


def two_column_frame(
    left_group: Mobject,
    right_group: Mobject,
    *,
    top_y: float,
    bottom_y: float,
    left_x: float = -6.66,
    right_x: float = 6.66,
    gap: float = 0.50,
    align_top: bool = False,
    min_scale: float = MIN_READABLE_SCALE,
) -> VGroup:
    """可选双栏协同排版：确保左右两栏围绕画布中心均衡分布，且不突破可读字号底线。"""
    max_h = max(0.35, float(top_y) - float(bottom_y))
    max_w = max(1.0, float(right_x) - float(left_x))
    if gap >= max_w:
        raise EngineError("LAYOUT_COLUMN_GAP_TOO_LARGE")
    # Compute all required scales before modifying either object.
    scales = [min(1.0, max_h / max(g.height, 1e-8)) for g in (left_group, right_group)]
    scaled_width = sum(g.width * s for g, s in zip((left_group, right_group), scales))
    common = min(1.0, (max_w - gap) / max(scaled_width, 1e-8))
    scales = [s * common for s in scales]
    if any(s + 1e-8 < _layout_floor(g, min_scale) for g, s in zip((left_group, right_group), scales)):
        raise EngineError("LAYOUT_COLUMNS_TOO_SMALL: 请改用单栏、重新分行或切幕")
    for g, s in zip((left_group, right_group), scales):
        _layout_scale(g, s)
    total_w = left_group.width + gap + right_group.width

    mid_x = (float(left_x) + float(right_x)) / 2.0
    if total_w >= max_w * 0.65:
        # 左栏对齐题干左起基准线，右栏自然舒展贴近右安全边（限制中缝过宽），
        # 既防止右栏加减卡片造成左栏横跳，又避免右侧留出大片空白带。
        start_x = float(left_x)
        gutter = min(1.85, max(gap, max_w - left_group.width - right_group.width))
        right_start_x = max(
            start_x + left_group.width + gap,
            min(float(right_x) - right_group.width, start_x + left_group.width + gutter),
        )
    else:
        start_x = mid_x - total_w / 2.0
        right_start_x = start_x + left_group.width + gap

    max_col_h = max(left_group.height, right_group.height)
    band_mid_y = (float(top_y) - max_col_h / 2.0) if align_top else (float(top_y) + float(bottom_y)) / 2.0

    left_group.move_to([start_x + left_group.width / 2.0, band_mid_y, 0.0])
    right_group.move_to([
        right_start_x + right_group.width / 2.0,
        band_mid_y,
        0.0,
    ])
    if align_top:
        left_group.shift(UP * (float(top_y) - left_group.get_top()[1]))
        right_group.shift(UP * (float(top_y) - right_group.get_top()[1]))
    return VGroup(left_group, right_group)


def highlight_clause(
    scene,
    *mobjs: Mobject,
    mobj: Mobject | None = None,
    color: str = HIGHLIGHT_BLUE,
    restore_color: str = INK_BLACK,
) -> None:
    """在当前 cue 内依次或整段标亮目标对象，结束前恢复原色。须直接调用 `highlight_clause(self, mobj)`，不可包进 `self.play(...)`。"""
    targets = [m for m in mobjs if m is not None]
    if mobj is not None:
        targets.insert(0, mobj)
    if not targets or not hasattr(scene, "cue_time_left") or not hasattr(scene, "wait"):
        raise TypeError(
            "highlight_clause(self, mobj) 第 1 参数必须是 AuthoredScene 实例 self，"
            "且请直接调用勿包裹在 self.play(...) 内"
        )
    left = max(0.0, float(scene.cue_time_left()) - 0.12)
    per = left / len(targets) if left > 0.05 else 0.0
    for target in targets:
        target.set_color(color)
        if per > 0.05:
            scene.wait(per)
        target.set_color(restore_color)


def board_note(
    *lines,
    color: str = HIGHLIGHT_BLUE,
    font_size: float = 22,
    line_buff: float = 0.14,
) -> VGroup:
    """无厚边框的轻量黑板旁注（细竖线 + 短句/公式），占高小、贴近真实手写板书。"""
    rows = [_normalize_card_line(item, body_size=font_size) for item in lines]
    rows = [r for r in rows if len(r) > 0 or not isinstance(r, VGroup)]
    if not rows:
        return VGroup()
    text_grp = VGroup(*rows).arrange(DOWN, aligned_edge=LEFT, buff=line_buff)
    bar = Line(
        [0.0, text_grp.get_top()[1] + 0.04, 0.0],
        [0.0, text_grp.get_bottom()[1] - 0.04, 0.0],
        color=color,
        stroke_width=4.0,
    )
    bar.next_to(text_grp, LEFT, buff=0.16)
    return VGroup(bar, text_grp)


def fit_stem(
    stem: Mobject,
    bounds: dict[str, float],
    *,
    max_height: float = 1.85,
    align_left: bool = False,
) -> Mobject:
    """将顶部题干或当前小问限制在顶部安全高度内；默认优先视觉居中，仅在右侧接近水印区时最小左移避让。"""
    top_y = float(bounds["stem_top_y"])
    fit_into_region(
        stem,
        top_y=top_y,
        bottom_y=top_y - max(0.8, float(max_height)),
        left_x=bounds["stem_left_x"],
        right_x=bounds["stem_right_x"],
        center_x=0.0,
        align_left=align_left,
        align_top=True,
    )
    if not align_left:
        safe_x = max(
            float(bounds["stem_left_x"]) + stem.width / 2.0,
            min(0.0, float(bounds["stem_right_x"]) - stem.width / 2.0),
        )
        stem.set_x(safe_x)
    return stem


def option_elimination_board(
    items: list[tuple[str, str, str]],
    *,
    title: str = "选项辨析与排雷",
    width: float = 4.9,
    title_size: float = 23,
    body_size: float = 21,
) -> VGroup:
    """选择题右侧排雷板：items 为 [(选项字母/表达式, 状态 'ok'|'bad'|'pending', 简短依据), ...]。"""
    lines = []
    for opt, status, reason in items:
        if status == "ok":
            mark = Text("✓", color="#0F766E", font_size=body_size, weight="BOLD")
        elif status == "bad":
            mark = Text("✗", color="#B91C1C", font_size=body_size, weight="BOLD")
        else:
            mark = Text("•", color=INK_MUTED, font_size=body_size)
        row = mixed_text(
            mark,
            ("m", f"({opt.strip('()')})"),
            ("t", f" {reason}" if reason else ""),
            font_size=body_size,
            color=INK_DARK,
        )
        lines.append(row)
    return aside_card(
        title,
        *lines,
        kind="guide",
        width=width,
        title_size=title_size,
        body_size=body_size,
        line_buff=0.14,
    )


def math_axes_box(
    x_range: list[float] | tuple[float, ...],
    y_range: list[float] | tuple[float, ...],
    *,
    x_length: float = 4.6,
    y_length: float = 3.4,
    x_label: str = "x",
    y_label: str = "y",
    font_size: int = 20,
) -> tuple[Axes, VGroup]:
    """白底深色坐标轴与外置轴标，防止几何/函数题坐标文字丢失或重叠。"""
    axes = Axes(
        x_range=list(x_range),
        y_range=list(y_range),
        x_length=x_length,
        y_length=y_length,
        axis_config={"color": INK_DARK, "stroke_width": 2.0, "include_tip": True, "tip_length": 0.16},
        tips=True,
    )
    xlab = MathTex(x_label, color=INK_BLACK).scale(0.54 * (font_size / 20.0))
    ylab = MathTex(y_label, color=INK_BLACK).scale(0.54 * (font_size / 20.0))
    xlab.next_to(axes.x_axis.get_end(), RIGHT, buff=0.12)
    ylab.next_to(axes.y_axis.get_end(), UP, buff=0.12)
    labels = VGroup(xlab, ylab)
    group = VGroup(axes, labels)
    group._wg_role = "axes"  # type: ignore[attr-defined]
    return axes, group


def active_pointer(
    target: Mobject,
    *,
    color: str = HIGHLIGHT_BLUE,
    buff: float = 0.14,
) -> Text:
    """在不改变已有黑字步骤对比度的前提下，在当前焦点行左侧生成轻量指示箭头。"""
    family = _safe_font_family()
    kw = {"font": family} if family else {}
    ptr = Text("▸", color=color, font_size=22, **kw)
    ptr.next_to(target, LEFT, buff=buff)
    return ptr


def mcq_options_grid(
    options: list[Mobject],
    *,
    max_width: float = 10.4,
    font_size: float = 24,
    h_buff: float = 0.45,
    v_buff: float = 0.14,
) -> VGroup:
    """考研选择题四个选项自适应 4 列 / 2x2 / 4 行排布，避免竖排占满半屏。"""
    items = [o if isinstance(o, Mobject) else mixed_text(("t", str(o)), font_size=font_size, color=INK_BLACK)
             for o in options]
    if not items:
        return VGroup()
    max_item_w = max(it.width for it in items)
    if len(items) == 4 and max_item_w * 4 + h_buff * 3 <= max_width:
        return VGroup(*items).arrange(RIGHT, buff=h_buff)
    if len(items) == 4 and max_item_w * 2 + h_buff <= max_width:
        col_w = (max_width - h_buff) / 2.0
        top = VGroup(items[0], items[1]).arrange(RIGHT, buff=max(h_buff, col_w - items[0].width))
        bot = VGroup(items[2], items[3]).arrange(RIGHT, buff=max(h_buff, col_w - items[2].width))
        bot.align_to(top, LEFT)
        items[3].set_x(items[1].get_left()[0] + items[3].width / 2.0)
        return VGroup(top, bot).arrange(DOWN, aligned_edge=LEFT, buff=v_buff)
    return VGroup(*items).arrange(DOWN, aligned_edge=LEFT, buff=v_buff)


def matrix_chain(
    matrices: list[str],
    arrows: list[str] | None = None,
    *,
    max_width: float = 12.2,
    scale: float = 0.56,
    h_buff: float = 0.22,
    v_buff: float = 0.28,
    color: str = INK_BLACK,
) -> VGroup:
    """线性代数矩阵初等行变换链：按宽度自动换行，防止多矩阵横排缩糊。"""
    arrows = list(arrows or [])
    tokens: list[Mobject] = []
    for idx, tex in enumerate(matrices):
        if idx > 0:
            op = arrows[idx - 1] if idx - 1 < len(arrows) else ""
            arr = MathTex(rf"\xrightarrow{{{op}}}" if op else r"\longrightarrow", color=HIGHLIGHT_BLUE).scale(scale * 0.95)
            tokens.append(arr)
        tokens.append(MathTex(tex, color=color).scale(scale))

    rows: list[list[Mobject]] = [[]]
    cur_w = 0.0
    for idx, tok in enumerate(tokens):
        step_w = tok.width + (h_buff if rows[-1] else 0.0)
        if rows[-1] and cur_w + step_w > max_width:
            rows.append([tok])
            cur_w = tok.width
        else:
            rows[-1].append(tok)
            cur_w += step_w
    row_groups = [VGroup(*r).arrange(RIGHT, buff=h_buff) for r in rows if r]
    return VGroup(*row_groups).arrange(DOWN, aligned_edge=LEFT, buff=v_buff)


def sign_chart(
    intervals: list[str],
    top_label: str,
    signs: list[str],
    bottom_label: str = "",
    trends: list[str] | None = None,
    *,
    col_width: float = 1.85,
    row_height: float = 0.58,
    font_size: float = 21,
) -> VGroup:
    """高数单调性/极值/凹凸性符号表（区间行 + 导数符号行 + 趋势/极值行）。"""
    family = _safe_font_family()
    kw = {"font": family} if family else {}
    n_cols = len(intervals) + 1
    total_w = n_cols * col_width
    row_data: list[tuple[str, list[str]]] = [
        ("x", intervals),
        (top_label, signs),
    ]
    if bottom_label or trends:
        row_data.append((bottom_label or "f(x)", list(trends or [""] * len(intervals))))
    n_rows = len(row_data)
    total_h = n_rows * row_height

    frame = Rectangle(
        width=total_w, height=total_h,
        stroke_color=INK_DARK, stroke_width=1.6,
        fill_color="#FFFFFF", fill_opacity=1.0,
    )
    grid_lines: list[Mobject] = [frame]
    for r in range(1, n_rows):
        y = total_h / 2.0 - r * row_height
        grid_lines.append(Line([-total_w / 2.0, y, 0], [total_w / 2.0, y, 0], color=INK_DARK, stroke_width=1.2))
    for c in range(1, n_cols):
        x = -total_w / 2.0 + c * col_width
        grid_lines.append(Line([x, total_h / 2.0, 0], [x, -total_h / 2.0, 0], color=INK_DARK, stroke_width=1.2))

    cells: list[Mobject] = []
    math_scale = 0.54 * (font_size / 21.0)
    for r_idx, (head_tex, vals) in enumerate(row_data):
        y = total_h / 2.0 - (r_idx + 0.5) * row_height
        h_obj = MathTex(head_tex, color=INK_BLACK).scale(math_scale)
        h_obj.move_to([-total_w / 2.0 + 0.5 * col_width, y, 0])
        cells.append(h_obj)
        for c_idx, val in enumerate(vals):
            x = -total_w / 2.0 + (c_idx + 1.5) * col_width
            txt = str(val).strip()
            if txt.isascii() and txt:
                cell = MathTex(txt, color=HIGHLIGHT_BLUE if txt in ("+", "-") else INK_BLACK).scale(math_scale)
            else:
                cell = Text(txt or " ", color=INK_BLACK, font_size=font_size, **kw)
            if cell.width > col_width - 0.16:
                cell.scale((col_width - 0.16) / cell.width)
            cell.move_to([x, y, 0])
            cells.append(cell)
    return VGroup(*grid_lines, *cells)


def integral_area_with_sweep(
    axes: Axes,
    lower_fn,
    upper_fn,
    x_range: tuple[float, float],
    *,
    sweep_x: float | None = None,
    lower_label: str = "",
    upper_label: str = "",
    fill_color: str = "#BFDBFE",
    fill_opacity: float = 0.45,
    arrow_color: str = HIGHLIGHT_BLUE,
) -> VGroup:
    """考研积分三件套：边界曲线填充阴影 + 垂直穿线箭头 + 白底衬垫防压线标签。"""
    x0, x1 = float(x_range[0]), float(x_range[1])
    low_curve = axes.plot(lower_fn, x_range=[x0, x1], color=INK_BLACK, stroke_width=2.2)
    up_curve = axes.plot(upper_fn, x_range=[x0, x1], color=INK_BLACK, stroke_width=2.2)
    area = axes.get_area(up_curve, x_range=[x0, x1], bounded_graph=low_curve, color=fill_color, opacity=fill_opacity)
    parts: list[Mobject] = [area, low_curve, up_curve]

    sx = float(sweep_x if sweep_x is not None else (x0 + x1) / 2.0)
    p_bot = axes.coords_to_point(sx, float(lower_fn(sx)))
    p_top = axes.coords_to_point(sx, float(upper_fn(sx)))
    sweep_arrow = Arrow(p_bot, p_top, buff=0.04, color=arrow_color, stroke_width=3.0, tip_length=0.16)
    parts.append(sweep_arrow)

    def _backed_label(tex: str, anchor, direction) -> Mobject:
        lbl = MathTex(tex, color=INK_BLACK).scale(0.56)
        lbl.next_to(anchor, direction, buff=0.14)
        bg = BackgroundRectangle(lbl, color="#FFFFFF", fill_opacity=0.92, buff=0.05)
        return VGroup(bg, lbl)

    if upper_label:
        parts.append(_backed_label(upper_label, up_curve.get_top(), UP))
    if lower_label:
        parts.append(_backed_label(lower_label, low_curve.get_bottom(), DOWN))
    group = VGroup(*parts)
    group._wg_role = "plot_item"  # type: ignore[attr-defined]
    return group


__all__ = [
    "INK_BLACK",
    "INK_DARK",
    "INK_MUTED",
    "HIGHLIGHT_BLUE",
    "MIN_READABLE_SCALE",
    "CARD_THEMES",
    "board_bounds",
    "board_note",
    "mixed_text",
    "aside_card",
    "fit_into_region",
    "fit_stem",
    "two_column_frame",
    "highlight_clause",
    "option_elimination_board",
    "math_axes_box",
    "active_pointer",
    "mcq_options_grid",
    "matrix_chain",
    "sign_chart",
    "integral_area_with_sweep",
]
