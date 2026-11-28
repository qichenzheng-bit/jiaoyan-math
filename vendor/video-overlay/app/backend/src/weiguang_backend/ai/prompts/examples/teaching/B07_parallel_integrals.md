# B07 parallel_integrals

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

分别构造 col1, col2, col3 的计算链，按实际宽度排成 VGroup(col1,col2,col3).arrange(RIGHT,buff=0.45,aligned_edge=UP)，先检查三列是否可读，逐列讲解。最后在下方汇总，不为并行布局人为拆分本来无需拆分的积分。
