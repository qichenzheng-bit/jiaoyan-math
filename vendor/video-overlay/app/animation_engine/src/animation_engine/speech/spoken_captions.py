"""Independent subtitle layer: Chinese Text + mathematical MathTex + timed SRT.

Subtitles are not AI-authored Manim scene elements.  Style is a validated
presentation setting and changing it never edits the educational scene code.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from ..core.video_settings import (
    CAPTION_BAND_HEIGHT_PX, CAPTION_BAND_TOP_PX, DEFAULT_VIDEO_FPS,
    PX_PER_UNIT, VIDEO_HEIGHT, VIDEO_WIDTH,
)
from ..core.video_settings import CAPTION_IMAGE_SIZE as _CAPTION_IMAGE_SIZE
from ..errors import EngineError
from ..infra.fonts import cjk_text_font_family
from ..render.mathtex_renderer import validate_math_latex
from .subtitle_style import FONT_FAMILIES, normalize_subtitle_style

CAPTION_BAND_TOP = CAPTION_BAND_TOP_PX
CAPTION_BAND_HEIGHT = CAPTION_BAND_HEIGHT_PX
CAPTION_IMAGE_SIZE = _CAPTION_IMAGE_SIZE
# 字幕里的公式与中文字高必须一致：28pt 中文约 0.355 高，MathTex 需放大到 0.64。
_BASE_MATH_SCALE = .64
# 参考课堂实测：字幕字号约为正文的 1.2–1.3 倍（正文 3.5% 屏高，字幕 4.2%–4.5%）。
_BASE_FONT_SIZE = 28

# 字幕里的符号统一换成 LaTeX：°、²、≥、√、π 这些必须是数学排版，不能画成
# 系统字体里的普通字符（那会把下标、根号、度数排得很丑）。
_UNICODE_TEX = {
    "°": r"^{\circ}", "²": "^{2}", "³": "^{3}", "¹": "^{1}", "ⁿ": "^{n}",
    "×": r"\times{}", "÷": r"\div{}", "±": r"\pm{}",
    "≥": r"\geq{}", "≤": r"\leq{}", "≠": r"\neq{}", "≈": r"\approx{}",
    "⋯": r"\cdots{}",
    "π": r"\pi{}", "∞": r"\infty{}",
    "α": r"\alpha{}", "β": r"\beta{}", "γ": r"\gamma{}", "δ": r"\delta{}",
    "ε": r"\varepsilon{}", "ζ": r"\zeta{}", "η": r"\eta{}", "θ": r"\theta{}",
    "κ": r"\kappa{}", "λ": r"\lambda{}", "μ": r"\mu{}", "ν": r"\nu{}",
    "ξ": r"\xi{}", "ρ": r"\rho{}", "σ": r"\sigma{}", "τ": r"\tau{}",
    "φ": r"\varphi{}", "ϕ": r"\phi{}", "χ": r"\chi{}", "ψ": r"\psi{}", "ω": r"\omega{}",
    "Γ": r"\Gamma{}", "Δ": r"\Delta{}", "Θ": r"\Theta{}", "Λ": r"\Lambda{}",
    "Ξ": r"\Xi{}", "Σ": r"\Sigma{}", "Φ": r"\Phi{}", "Ψ": r"\Psi{}", "Ω": r"\Omega{}",
    "∠": r"\angle{}", "△": r"\triangle{}", "⊥": r"\perp{}", "∥": r"\parallel{}",
    "∵": r"\because{}", "∴": r"\therefore{}", "∈": r"\in{}", "∉": r"\notin{}",
    "∪": r"\cup{}", "∩": r"\cap{}", "′": "'",
    "∂": r"\partial{}", "∮": r"\oint{}", "∬": r"\iint{}", "∫": r"\int{}",
}

_COMBINING_MATH = {
    "\u0302": "hat",
    "\u0304": "bar",
    "\u0303": "tilde",
    "\u0307": "dot",
    "\u0308": "ddot",
    "\u20d7": "vec",
}
_COMBINING_CHARS = "".join(_COMBINING_MATH)
_COMBINING_RE = re.compile(rf"([A-Za-z0-9\u0391-\u03C9])([{_COMBINING_CHARS}]+)")
_ORPHAN_COMBINING_RE = re.compile(r"[\u0300-\u036f\u20d0-\u20ff]")

# 归一化之后的数学片段（字母/数字/命令/运算符连续串）。
# 允许以 { 起始：口播里的概率事件写法 P{X≤3}、{X≤x} 属于数学记号，
# 由 _literal_braces 渲染成可见花括号，而不是当原始 TeX 拒绝掉。
_MATH_RUN = re.compile(
    r"(?:\((?=[A-Za-z0-9\\\-])|[A-Za-z0-9\\{])"
    r"[A-Za-z0-9\\^_=+\-*/<>().,\[\]{}|'′₀-₉⁰-⁹]{0,120}")

_SUBSCRIPT = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def _normalize_math_symbols(text: str) -> str:
    # 先处理字母/希腊字母 + Unicode 组合变音符（如 θ̂ = θ + \u0302 → \hat{\theta}），
    # 避免组合符脱离基底字符在 Text 里画成虚线圆圈乱码 ◌̂。
    def _fold_combining(match: re.Match[str]) -> str:
        base, marks = match.group(1), match.group(2)
        tex_base = _UNICODE_TEX.get(base, base)
        if tex_base.endswith("{}"):
            tex_base = tex_base[:-2]
        out = tex_base
        for mark in marks:
            cmd = _COMBINING_MATH.get(mark)
            if cmd:
                out = rf"\{cmd}{{{out}}}"
        return out

    text = _COMBINING_RE.sub(_fold_combining, text)
    text = _ORPHAN_COMBINING_RE.sub("", text)
    # 根号必须带参数：√3 → \sqrt{3}，孤立的 √ 用空参数，避免编译失败
    text = re.sub(r"√\s*([A-Za-z0-9])", r"\\sqrt{\1}", text)
    text = text.replace("√", r"\sqrt{}")
    # 带上下标的 Σ_(...) / Π_(...) 用大算子 \sum / \prod，避免 \Sigma{}_ 无法对齐上下限
    text = re.sub(r"Σ(?=\s*[_^])", r"\\sum", text)
    text = re.sub(r"Π(?=\s*[_^])", r"\\prod", text)
    return "".join(_UNICODE_TEX.get(ch, ch) for ch in text)


_UNIT_POWER = re.compile(r"^([A-Za-z]{2,})(\^\{?[0-9]+\}?)$")
_OPERATOR_WORDS = ("arcsin", "arccos", "arctan", "sin", "cos", "tan", "cot",
                   "sec", "log", "ln", "lim", "max", "min", "exp")
_OPERATOR_RE = re.compile(
    r"(?<![\\A-Za-z])(" + "|".join(_OPERATOR_WORDS) + r")(?![A-Za-z])")


_FOLD_SUB = re.compile(r"[₀-₉]+")
_FOLD_SUP = re.compile(r"[⁰-⁹]+")
_CMD = re.compile(r"\\[A-Za-z]+\*?|\\.")


def _fold_scripts(token: str) -> str:
    """Unicode 上下标数字（x₁、x²）在数学 token 内转成 LaTeX 上下标。"""
    token = _FOLD_SUB.sub(
        lambda m: "_{" + m.group(0).translate(_SUBSCRIPT) + "}", token)
    return _FOLD_SUP.sub(
        lambda m: "^{" + m.group(0).translate(_SUPERSCRIPT) + "}", token)


def _literal_braces(token: str) -> str:
    """让口播里的 { } 变成画面可见的数学花括号。

    LaTeX 语法里的花括号是参数：`\\leq{}`、`\\sqrt{3}`、`x_{1}` 原样保留；
    概率事件写法 P{X≤3}、{X≤x} 的花括号转义成 `\\{ ... \\}`，不再被判成原始 TeX。
    """
    out: list[str] = []
    stack: list[bool] = []
    i = 0
    while i < len(token):
        match = _CMD.match(token, i)
        if match:
            out.append(match.group(0))
            i = match.end()
            continue
        char = token[i]
        if char == "{":
            prev = out[-1] if out else ""
            group = bool(_CMD.fullmatch(prev)) or prev in ("_", "^")
            stack.append(group)
            out.append("{" if group else r"\{")
        elif char == "}":
            group = stack.pop() if stack else False
            out.append("}" if group else r"\}")
        else:
            out.append(char)
        i += 1
    return "".join(out)


_INLINE_FRAC_RE = re.compile(
    r"(?<![A-Za-z0-9_\\])"
    r"(\([^()]+\)|\\[A-Za-z]+(?:\{\})?(?:\^\{[^}]+\}|_\{[^}]+\})?|[A-Za-z0-9]+(?:\^\{[^}]+\}|_\{[^}]+\}|\^[A-Za-z0-9]|_[A-Za-z0-9])?)"
    r"\s*/\s*"
    r"(\([^()]+\)|\\[A-Za-z]+(?:\{\})?(?:\^\{[^}]+\}|_\{[^}]+\})?|[A-Za-z0-9]+(?:\^\{[^}]+\}|_\{[^}]+\}|\^[A-Za-z0-9]|_[A-Za-z0-9])?)"
    r"(?![A-Za-z0-9_^{])"
)


def _replace_inline_fractions(token: str) -> str:
    """将字幕中的简单斜线分式（如 θ/n、1/2、(x+1)/(x-1)）转写为标准 \\frac，保留微商记号不变。"""
    if "/" not in token or r"\partial" in token or re.search(r"(?:^|[^A-Za-z])d[A-Za-z]/d[A-Za-z]", token):
        return token

    def _sub(match: re.Match[str]) -> str:
        num, den = match.group(1), match.group(2)
        if num.startswith("(") and num.endswith(")"):
            num = num[1:-1]
        if den.startswith("(") and den.endswith(")"):
            den = den[1:-1]
        return rf"\frac{{{num}}}{{{den}}}"

    return _INLINE_FRAC_RE.sub(_sub, token)


def _normalize_token(token: str) -> str:
    token = _fold_scripts(token)
    token = token.replace("->", r"\to{}").replace(">=", r"\geq{}").replace("<=", r"\leq{}")
    token = re.sub(r"\^\(([^()]+)\)", r"^{\1}", token)
    token = re.sub(r"_\(([^()]+)\)", r"_{\1}", token)
    token = _OPERATOR_RE.sub(lambda m: "\\" + m.group(1) + "{}", token)
    token = _literal_braces(token) if ("{" in token or "}" in token) else token
    return _replace_inline_fractions(token)


def _math_token(token: str) -> str | None:
    """单字母/数字、带运算符或上下标、字母+下标算数学；英文单词与单位不算。

    单位指数（cm²、m³）保留正体，包一层 \\mathrm，避免被排成斜体散字母。
    """
    if not token:
        return None
    if token.endswith(("^", "_")) or token.count("{") != token.count("}"):
        return None
    unit = _UNIT_POWER.match(token)
    if unit:
        base, power = unit.group(1), unit.group(2)
        if base in _OPERATOR_WORDS:
            return f"\\{base}{{}}{power}"
        return r"\mathrm{%s}%s" % (base, power)
    if "\\" in token:
        return _normalize_token(token)
    if token in _OPERATOR_WORDS:
        return "\\" + token + "{}"
    if any(ch in token for ch in "^_=+-*/<>()[]{}"):
        return _normalize_token(token)
    if all(ch.isdigit() or ch == "." for ch in token):
        return token
    if token in ("dx", "dy", "dz", "dt", "du", "dv", "ds", "dr"):
        return r"\mathrm{d}" + token[1]
    if re.fullmatch(r"\d+[A-Za-z]{1,2}", token):
        return token
    if len(token) == 1 and token.isalnum():
        return token
    if len(token) <= 4 and token[0].isalpha() and all(
            ch.isdigit() or ch == "'" for ch in token[1:]):
        return token
    return None


def split_mixed_caption(text: str) -> tuple[tuple[str, str], ...]:
    """Return literal Chinese Text segments and safe isolated MathTex pieces.

    字母、数字、公式一律交给 MathTex（与板书同一套 LaTeX 渲染），
    Unicode 数学符号先转成 LaTeX 命令，避免被画成普通字符。
    """
    normalized = _normalize_math_symbols(text)
    result: list[tuple[str, str]] = []
    cursor = 0
    for match in _MATH_RUN.finditer(normalized):
        start, end = match.start(), match.end()
        token = match.group()
        trail = ""
        while token and (
            token[-1] in ".,;:"
            or (token[-1] == ")" and token.count(")") > token.count("("))
            or (token[-1] == "]" and token.count("]") > token.count("["))
        ):
            trail = token[-1] + trail
            token = token[:-1]
        while token and (
            (token[0] == "(" and token.count("(") > token.count(")"))
            or (token[0] == "[" and token.count("[") > token.count("]"))
        ):
            token = token[1:]
            start += 1
        if token.count("(") != token.count(")") or token.count("[") != token.count("]"):
            continue
        latex = _math_token(token)
        if latex is None:
            continue
        latex = latex.replace("′", "'")
        try:
            validate_math_latex(latex)
        except (ValueError, TypeError):
            continue
        if start > cursor:
            result.append(("text", normalized[cursor:start]))
        result.append(("math", latex))
        if trail:
            result.append(("text", trail))
        cursor = end
    if cursor < len(text) or cursor < len(normalized):
        result.append(("text", normalized[cursor:]))
    return tuple(result) if result else (("text", normalized),)


def _safe_math_caption_break(tex: str) -> tuple[str, str] | None:
    depth = 0
    points = []
    for index, char in enumerate(tex):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == "=" and depth == 0 and 0 < index < len(tex) - 1:
            points.append(index)
    if not points:
        return None
    point = min(points, key=lambda value: abs(value - len(tex) / 2))
    return tex[:point+1], tex[point+1:]


def _caption_frame(kind: str, display: str, cfg: dict, *, math: str = ""):
    """构造一张字幕的 (底板, 字形)。规格与越界检查都集中在这。"""
    from manim import Text, MathTex, RoundedRectangle, VGroup, DOWN, RIGHT, WHITE, BLACK

    scale = cfg["font_scale"]
    # 字体/字色/描边由字幕样式决定（微调里可以改），默认值与原来的硬编码一致。
    family = FONT_FAMILIES.get(str(cfg.get("font_family") or "default"),
                              cjk_text_font_family()) or cjk_text_font_family()
    ink = str(cfg.get("text_color") or "#111827")
    math_ink = "#1E3A8A" if ink.upper() == "#111827" else ink
    stroke_width = float(cfg.get("stroke_width") or 0.0)
    stroke_color = str(cfg.get("stroke_color") or "")
    if kind == "math":
        glyph = MathTex(display, color=math_ink).scale(_BASE_MATH_SCALE * scale)
    else:
        fragments = split_mixed_caption(display)
        objects = []
        punct_flags = []
        for fragment_kind, text in fragments:
            # 纯空白片段（"x y" 中间那个空格）会构造出零宽 Text：Manim 的
            # arrange 用"前一个的右边界"逐个定位，碰到零宽对象会把后半句重新
            # 居中，于是两串字叠在一起（22s/25s 字幕重叠就是这么来的）。
            if not text.strip():
                continue
            if fragment_kind == "math":
                objects.append(
                    MathTex(text, color=math_ink).scale(_BASE_MATH_SCALE * scale))
                punct_flags.append(False)
            else:
                objects.append(Text(
                    text, font=family,
                    color=ink, font_size=_BASE_FONT_SIZE * scale,
                ))
                punct_flags.append(all(ch in "，。！？；：、,.!?;: " for ch in text))
        if not objects:
            objects.append(Text(display, font=family,
                                color=ink, font_size=_BASE_FONT_SIZE * scale))
            punct_flags.append(False)
        if len(objects) > 1:
            glyph = VGroup(*objects).arrange(RIGHT, buff=.025)
            # 孤立中文标点（如紧跟在公式后面的 "。" / "，"）默认按高度居中会飘到字腰变成 °；
            # 这里按常规中文字的底线拉齐，并保留标点自身的轻微下沉。
            if any(punct_flags):
                baseline_ref = next(
                    (obj for obj, is_p in zip(objects, punct_flags)
                     if not is_p and isinstance(obj, Text)),
                    None,
                )
                if baseline_ref is None:
                    baseline_ref = Text("国", font=family, color=ink, font_size=_BASE_FONT_SIZE * scale)
                    baseline_ref.set_y(glyph.get_center()[1])
                ref_bottom = baseline_ref.get_bottom()[1]
                for obj, is_p in zip(objects, punct_flags):
                    if is_p:
                        obj.set_y(ref_bottom + obj.height * 0.5 + 0.02 * scale)
        else:
            glyph = objects[0]
    if math and kind != "math":
        # 中文始终与声音对应，数学字幕作为第二行，不再替代中文。
        math_glyph = MathTex(math, color=math_ink).scale(.48 * scale)
        if math_glyph.width > 11.9:
            math_glyph.scale(11.9 / math_glyph.width)
        glyph = VGroup(glyph, math_glyph).arrange(DOWN, buff=.12 * scale)
    plate_height = .62 * scale
    if kind == "math":
        if glyph.width > 12.6:
            pieces = _safe_math_caption_break(display)
            if pieces is None:
                raise EngineError("CAPTION_MATH_NEEDS_REVIEWED_BREAK")
            glyph = VGroup(*(
                MathTex(part, color=ink)
                for part in pieces
            )).arrange(DOWN, buff=.08)
            glyph.scale(min(.44 * scale, 12.4 / glyph.width,
                            1.35 / glyph.height))
            plate_height = 1.6 * scale
        if glyph.height > .47 * scale:
            plate_height = max(plate_height, glyph.height + .16)
    if glyph.width > 12.6:
        glyph.scale(12.4 / glyph.width)
    if stroke_width > 0 and stroke_color:
        # 描边宽度按像素给，换算成 Manim 单位（1 单位 = PX_PER_UNIT 像素）
        glyph.set_stroke(stroke_color, width=stroke_width / PX_PER_UNIT)
    if glyph.height > 1.70 or glyph.width > 12.6:
        raise EngineError(
            f"CAPTION_LINE_TOO_LONG:{kind}:{glyph.width:.3f}x{glyph.height:.3f}")
    plate_height = max(plate_height, glyph.height + .14)
    # Reject a plate that cannot fit instead of clipping its glyphs at compositing.
    max_plate_height = (VIDEO_HEIGHT - CAPTION_BAND_TOP) / PX_PER_UNIT - .10
    if plate_height > max_plate_height + 1e-8:
        raise EngineError("CAPTION_SAFE_REGION_TOO_SMALL: 请合理分段数学字幕")
    # Offsets are independent of scene code and are in source pixels.
    # Anchor bottom edge steadily so tall vertical fractions expand smoothly upward instead of bouncing.
    desired_center = -3.90 + plate_height / 2 + cfg["vertical_offset_px"] / PX_PER_UNIT
    # Keep large fractions and two-line formula captions fully
    # inside the configured subtitle strip; never crop glyphs.
    band_top_y = 4.0 - CAPTION_BAND_TOP / PX_PER_UNIT
    center = min(band_top_y - 0.05 - plate_height / 2,
                 max(-3.95 + plate_height / 2, desired_center))
    glyph.move_to([0, center, 0])
    plate = RoundedRectangle(
        width=max(1., glyph.width + .36),
        height=plate_height, corner_radius=.09,
        fill_color=WHITE,
        fill_opacity=cfg["background_opacity"],
        stroke_color="#CBD5E1", stroke_width=.35,
    ).move_to([0, center, 0])
    return plate, glyph


def render_caption_pngs(items, *, style: dict | None = None,
                        on_progress=None, cancel_check=None) -> None:
    """一次 Manim 会话批量出图。

    items 是 [(kind, display, output_path[, math_latex]), ...]。

    以前每张字幕都单独起一个 Manim 场景（重新初始化 renderer、重新加载字体、
    走一遍 render 流程），实测 87 张要 4 分钟；这里在同一个 tempconfig 里
    依次构造、取帧、落盘，把 87 次初始化压成 1 次，且不增加任何计算量。
    """
    rows = []
    for item in items:
        if len(item) == 3:
            kind, display, output = item
            math = ""
        elif len(item) == 4:
            kind, display, output, math = item
        else:
            raise EngineError("CAPTION_ITEM_FORMAT_INVALID")
        rows.append((kind, display, Path(output), math or ""))
    if not rows:
        return
    for kind, display, _, math in rows:
        if kind not in ("text", "math") or not display:
            raise EngineError("CAPTION_UNVERIFIED_SOURCE")
        if kind == "math":
            validate_math_latex(display)
        if math:
            validate_math_latex(math)
        if kind != "math" and any(char in display for char in ("\\", "$")):
            raise EngineError("CAPTION_PHONETIC_OR_RAW_TEX")
        elif any(char in display for char in ("{", "}")):
            if any(
                frag_kind == "text" and any(ch in frag_text for ch in ("\\", "$", "{", "}"))
                for frag_kind, frag_text in split_mixed_caption(display)
            ):
                raise EngineError("CAPTION_PHONETIC_OR_RAW_TEX")
    cfg = normalize_subtitle_style(style)
    try:
        from manim import Scene, tempconfig
    except ImportError as exc:
        raise EngineError("CAPTION_MANIM_REQUIRED") from exc
    from PIL import Image

    for _, _, output, _ in rows:
        output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="wg-caption-") as folder:
        root = Path(folder)
        with tempconfig({
            "pixel_width": VIDEO_WIDTH, "pixel_height": VIDEO_HEIGHT,
            "frame_width": VIDEO_WIDTH / PX_PER_UNIT, "frame_height": 8,
            "frame_rate": DEFAULT_VIDEO_FPS, "background_color": "#FFFFFF",
            "transparent": True, "format": "png",
            "save_last_frame": False, "write_to_movie": False,
            "media_dir": str(root), "output_file": "source_math_subtitle",
            "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR",
        }):
            class BatchCaptionScene(Scene):
                def construct(self):
                    total = len(rows)
                    for idx, (kind, display, output, math) in enumerate(rows, start=1):
                        if cancel_check is not None:
                            cancel_check()
                        plate, glyph = _caption_frame(kind, display, cfg, math=math)
                        self.add(plate, glyph)
                        self.renderer.update_frame(self)
                        frame = self.renderer.get_frame()
                        image = (frame if isinstance(frame, Image.Image)
                                 else Image.fromarray(frame))
                        image = image.convert("RGBA")
                        if image.size != (VIDEO_WIDTH, VIDEO_HEIGHT):
                            raise EngineError("CAPTION_RENDERED_FRAME_SIZE")
                        image.crop((0, CAPTION_BAND_TOP, VIDEO_WIDTH,
                                    VIDEO_HEIGHT)).save(output)
                        self.remove(plate, glyph)
                        if on_progress is not None:
                            on_progress(idx, total)

            BatchCaptionScene().render()
    for _, _, output, _ in rows:
        if not output.is_file() or output.stat().st_size < 100:
            raise EngineError("CAPTION_MATHTEX_PNG_MISSING")


def render_caption_png(kind: str, display: str, output: Path,
                       *, style: dict | None = None) -> None:
    """渲染单张字幕图（走批量通道，保证与批量出图完全同一套代码）。"""
    render_caption_pngs([(kind, display, output)], style=style)


def captions_srt(cues: list[dict], *, fps: int) -> str:
    """Plain-text SRT follows the spoken sentence, never raw TeX source."""
    def fmt(frame):
        ms = round(frame * 1000 / fps)
        hh, ms = divmod(ms, 3600000)
        mm, ms = divmod(ms, 60000)
        ss, ms = divmod(ms, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"
    parts = []
    index = 0
    for cue in cues:
        display = ((cue.get("actual_voice_text") or "").strip()
                   if cue["kind"] == "math" else cue["display"])
        if not display:
            continue
        index += 1
        parts.append(
            f'{index}\n{fmt(cue["start_frame"])} --> '
            f'{fmt(cue["end_frame"])}\n{display}\n')
    return "\n".join(parts) + "\n"


__all__ = [
    "render_caption_png", "captions_srt", "split_mixed_caption",
    "CAPTION_BAND_TOP", "CAPTION_BAND_HEIGHT", "CAPTION_IMAGE_SIZE",
]
