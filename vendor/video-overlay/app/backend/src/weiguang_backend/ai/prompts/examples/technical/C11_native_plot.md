# C11 native_plot

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

axes=Axes(x_range=[-2,2,1],y_range=[0,4,1],axis_config={"color":BLACK}); graph=axes.plot(lambda x:x*x,x_range=[-2,2],color="#1D4ED8"); dot=Dot(axes.c2p(1,1),color=BLACK)。参数与坐标用数学关系计算。
