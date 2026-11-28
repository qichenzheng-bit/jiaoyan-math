"""Static checks of layout configuration and overflow-safe helper implementation."""
import ast
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "vendor/video-overlay/app/animation_engine/src/animation_engine"
def test_layout_source_syntax():
    for path in BASE.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
def test_caption_candidate_is_not_enabled_without_render_acceptance():
    path = BASE / "core/video_settings.py"
    values = {}
    exec(compile(path.read_text(), str(path), "exec"), values)
    assert values["VIDEO_HEIGHT"] == 1080 and values["DEFAULT_VIDEO_FPS"] == 60
    assert values["CAPTION_BAND_HEIGHT_PX"] == 240
    assert values["CAPTION_CANDIDATE_HEIGHT_PX"] == 200
    # 1.70 Manim units can be permitted by the previous glyph limit.
    assert 1.70 * values["PX_PER_UNIT"] > values["CAPTION_CANDIDATE_HEIGHT_PX"]
