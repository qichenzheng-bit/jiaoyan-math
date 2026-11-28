# B13 erase

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

新行的 bottom 超过 board_floor_y 时，先在下一有效 cue 内 FadeOut 已用完的对象；保留后续引用的关键式，再 Write 新行。不要在同一个 self.play 同时退旧内容和写新内容，不写死行数。
