# B09 error_compare

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

bad=MathTex(r"(A+B)^2=A^2+2AB+B^2",color="#B91C1C"); mark=Cross(bad,stroke_color="#B91C1C"); good=MathTex(r"(A+B)^2=A^2+AB+BA+B^2",color=BLACK)。明确标记 bad 是错误写法，解释矩阵通常不交换，错误演示结束后擦除。
