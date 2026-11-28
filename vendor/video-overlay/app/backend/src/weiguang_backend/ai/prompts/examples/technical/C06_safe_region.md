# C06 safe_region

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

bounds=board_bounds(watermark_safe_region_px=watermark_region,caption_safe_region_px=caption_region)；fit_stem(stem,bounds) 按实际安全区避让。watermark_region 与 caption_region 必须使用系统传入的真实字面量，不引用未定义变量。
