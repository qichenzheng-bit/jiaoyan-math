"""品牌水印设置：唯一的默认值、输入校验和1080p安全区域计算。

这里存的不是教学动画；用户的配置在最终 FFmpeg 合成时使用。
"""
from __future__ import annotations

from ..core.video_settings import (
    VIDEO_WIDTH, CAPTION_BAND_TOP_PX,
)

WATERMARK_DEFAULTS = {
    "enabled": True,
    "position": "top-right",
    "width_px": 260,
    "vertical_margin_px": 45,
    "horizontal_margin_px": 40,
    "opacity_percent": 80,
}
POSITIONS = frozenset({"top-left", "top-right", "bottom-left", "bottom-right"})
MAX_WIDTH_PX = 520
MIN_WIDTH_PX = 180
LOGO_ASPECT = 390 / 92
# 水印画布比Logo轮廓略高，防止边缘挤压；以340x96为默认预览框。
CANVAS_ASPECT = 340 / 96


def normalize_watermark_style(style: dict | None = None) -> dict:
    """拒绝非法输入；新/旧清单可只含部分字段。"""
    if style is None:
        style = {}
    if not isinstance(style, dict):
        raise ValueError("WATERMARK_STYLE_NOT_OBJECT")
    out = dict(WATERMARK_DEFAULTS)
    for key in WATERMARK_DEFAULTS:
        if key in style:
            out[key] = style[key]
    if type(out["enabled"]) is not bool:
        raise ValueError("WATERMARK_ENABLED_INVALID")
    if not isinstance(out["position"], str):
        raise ValueError("WATERMARK_POSITION_INVALID")
    out["position"] = out["position"].replace("_", "-")
    if out["position"] not in POSITIONS:
        raise ValueError("WATERMARK_POSITION_INVALID")
    for key, low, high in (
        ("width_px", MIN_WIDTH_PX, MAX_WIDTH_PX),
        ("vertical_margin_px", 0, 200),
        ("horizontal_margin_px", 0, 200),
        ("opacity_percent", 30, 100),
    ):
        val = out[key]
        if type(val) is not int or not low <= val <= high:
            raise ValueError("WATERMARK_CONFIG_INVALID: " + key)
    if out["width_px"] + out["horizontal_margin_px"] > VIDEO_WIDTH:
        raise ValueError("WATERMARK_OUT_OF_BOUNDS")
    if watermark_height(out) + out["vertical_margin_px"] > CAPTION_BAND_TOP_PX:
        raise ValueError("WATERMARK_OUT_OF_BOARD")
    return out


def watermark_height(style: dict) -> int:
    return round(style["width_px"] / CANVAS_ASPECT)


def watermark_rect(style: dict | None = None) -> dict:
    """左上角画布坐标与占位框。下方位置限定在字幕带上沿之上。"""
    s = normalize_watermark_style(style)
    w = s["width_px"]
    h = watermark_height(s)
    x = s["horizontal_margin_px"] if s["position"].endswith("left") else VIDEO_WIDTH - s["horizontal_margin_px"] - w
    y = s["vertical_margin_px"] if s["position"].startswith("top") else CAPTION_BAND_TOP_PX - s["vertical_margin_px"] - h
    return {"x": x, "y": y, "width": w, "height": h}


__all__ = ["WATERMARK_DEFAULTS", "normalize_watermark_style", "watermark_rect",
           "watermark_height", "LOGO_ASPECT"]
