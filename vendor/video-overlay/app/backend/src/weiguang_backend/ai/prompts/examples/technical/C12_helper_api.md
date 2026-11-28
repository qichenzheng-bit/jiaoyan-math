# C12 helper_api

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

axes, diagram = math_axes_box([0,2,1],[0,4,1],x_length=4.6,y_length=3.4)；integral_area_with_sweep(axes,lower_fn,upper_fn,x_range) 返回 VGroup，不是 Animation；highlight_clause(self, target) 直接调用，不放 self.play。以公共技术规范中的签名为准。
