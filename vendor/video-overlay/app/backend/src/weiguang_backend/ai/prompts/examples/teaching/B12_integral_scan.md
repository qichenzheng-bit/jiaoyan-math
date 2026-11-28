# B12 integral_scan

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

tracker=ValueTracker(0.3); sweep=always_redraw(lambda:Line(axes.c2p(tracker.get_value(),tracker.get_value()**2),axes.c2p(tracker.get_value(),tracker.get_value()),color="#B91C1C"))。在 0≤x≤1 区域演示 y 从 x² 到 x，扫描线与上下界实际一致。
