# B19 spatial_projection

参考片段（非独立可执行场景，变量需在 construct 中实际定义；尚未成片验证）。

AuthoredScene 当前继承 Scene，不默认拥有 ThreeDScene 相机接口。可用 Axes 或原生线段构造数学准确的二维投影示意，标出投影关系；不可调用未经核验的 set_camera_orientation 或虚构真实三维渲染能力。必要三维能力待实际引擎验证。
