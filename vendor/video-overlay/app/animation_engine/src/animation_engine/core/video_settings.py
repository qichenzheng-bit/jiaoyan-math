"""核心 · 帧率与时长策略

为什么要有这个文件：
    帧率散落在各处会导致"同一个 0.6 秒的擦板动作，在 30 FPS 下是 18 帧、
    在 60 FPS 下是 36 帧"这种隐形不一致。这里统一规定：**时长用秒表述，
    帧数在出口处按帧率换算**，任何地方都不得写死帧数。

默认 60 FPS 只针对新视频与新微调会话；老项目显式指定的低帧率继续支持，
否则历史视频重渲染结果会变。
"""
from __future__ import annotations

DEFAULT_VIDEO_FPS = 60      # 所有新输出统一 60 帧
MIN_VIDEO_FPS = 60          # 历史低帧率视频保留播放，新出片统一 60
MAX_VIDEO_FPS = 60          # 上限：目前渲染链路只验证到 60
BOARD_WIPE_SECONDS = 0.6    # 擦板动画时长（秒），与帧率无关

# 画面规格：1080p。以前散落在渲染入口、成片校验、字幕带裁剪、水印、缓存校验
# 等六七处的 1280×720 全部收敛到这里，改分辨率只需要改这一块。
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
MANIM_FRAME_HEIGHT = 8.0            # Manim 画面固定 8 个单位高，与像素无关
PX_PER_UNIT = VIDEO_HEIGHT / MANIM_FRAME_HEIGHT   # 135 px / 单位

# 字幕带：屏幕底部 240px（1080p 下为 840~1080px，Manim y = -2.22 ~ -4.0）。
# 将字幕带从 360px 收敛到 240px，为上方讲解板书多释放 +0.89 Manim 单位（+120px）纵深，
# 同时仍足以容纳双行分式大字字幕并避免底部紧压。
CAPTION_BAND_TOP_PX = 840
CAPTION_BAND_HEIGHT_PX = 240
# 200px is an acceptance-test candidate, not a production default.
CAPTION_CANDIDATE_HEIGHT_PX = 200
CAPTION_IMAGE_SIZE = (VIDEO_WIDTH, CAPTION_BAND_HEIGHT_PX)


# 品牌水印的所有可调整参数统一在 render.watermark_style 中。
# 这里仅保留视频尺寸与字幕安全区等通用编码参数。


# 场景中间产物（无声分镜 mp4）的编码参数。
# Manim 默认是 libx264 + crf23 且不指定 preset（x264 回落 medium）：1080p60 下
# 编码本身要吃掉三分之一以上的渲染时间。这里显式改成 veryfast + crf18：
# 编码快 3~4 倍，中间产物画质更高（最终成片还要再编一次，少一代损失）。
SCENE_ENCODER_OPTIONS = {"crf": "18", "preset": "veryfast"}

# Manim 片段（单次 play）级缓存的布局版本：改变缓存用法时 +1，让旧片段自然作废。
MANIM_SEGMENT_CACHE_VERSION = 2


def transition_frame_count(fps: int) -> int:
    """把 0.6 秒的擦板动作换算成指定帧率下的帧数。

    帧率非法直接抛错，不做静默纠正——悄悄改成 60 会让导出规格与用户预期不符。
    """
    if type(fps) is not int or fps != DEFAULT_VIDEO_FPS:
        raise ValueError("VIDEO_FPS_OUT_OF_RANGE")
    # 至少 1 帧：极低帧率下四舍五入可能得到 0，会导致空动画
    return max(1, round(BOARD_WIPE_SECONDS * fps))
