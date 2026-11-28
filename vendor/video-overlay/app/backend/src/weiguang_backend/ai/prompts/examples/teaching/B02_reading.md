# B02 reading

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

先按自然语义构造 stem = VGroup(c1, c2).arrange(DOWN, aligned_edge=LEFT, buff=0.24)，整体居中；每段用 mixed_text 构造，完整题干静态 add；读题 cue 内直接调用 highlight_clause(self, c1, c2)，不能包装在 self.play 内。短题干同一行，长题不缩成小字。
