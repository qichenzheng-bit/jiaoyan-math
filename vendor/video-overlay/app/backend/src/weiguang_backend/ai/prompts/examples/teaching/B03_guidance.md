# B03 guidance

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

以板书旁注呈现 I1/I2/I3，不显示编号。例：board_note(("m", r"\ln(1+x)\sim x"), ("t", "一次项抵消")) 之前先确认 board_note 真实行参数；更稳妥的写法是 board_note(MathTex(r"\ln(1+x)\sim x", color=BLACK), Text("一次项抵消", color=BLACK, font_size=24))。讲解为什么一阶不足，再转二阶。
