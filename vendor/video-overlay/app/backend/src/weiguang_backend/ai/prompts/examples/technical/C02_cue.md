# C02 cue

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

self.start_cue("s01_step","将 x 的平方写出来。","",tts_text="将 x 的平方写出来。")
self.play(Write(formula),run_time=min(0.8,self.cue_time_left()*0.5))
self.end_cue("s01_step")。仅在 construct 顶层成对出现，跨场景 cue_id 唯一。
