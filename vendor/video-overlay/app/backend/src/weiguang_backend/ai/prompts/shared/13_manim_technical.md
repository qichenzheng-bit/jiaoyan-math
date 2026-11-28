# Manim 技术接口与安全契约
只输出完整可执行 Python 场景，继承 AuthoredScene，定义 construct(self)，不覆盖保留方法或自定义 __init__。仅允许 manim、math、numpy、animation_engine 的合法接口；禁止文件网络系统、动态执行、危险反射等安全违规操作。固定1920×1080、60fps、字幕及水印安全区由系统控制，动画以秒为单位。MathTex/Tex 和数学混排用 ASCII LaTeX 原始字符串，命令后需空格防黏连，括号、环境配对，中文单独 Text。每个 start_cue/end_cue 在 construct 顶层成对出现，前三个参数字符串字面量，cue_id 字母数字下划线短横线且全课唯一。禁止 cue 放入循环、条件或子函数，禁止句间/末句后 play/wait/退场；开场前仅可静态 add。退场与新对象入场分开播放，放下一有效 cue 内。cue_time_left()/cue_elapsed() 控制时长，复杂动画拆 cue，不依赖引擎压缩；静态校验只检查语法、LaTeX 源码、接口、安全、锚点契约，不试渲染、不审核数学或教学内容。实际执行错误属于正式渲染。
重要布局按需 check_layout(label, question=..., working=..., pedagogy=...)；动态高风险段 watch_layout(label, **groups)，结束 stop_layout_watch(label)，传实际独立可见对象，不把整图数学上有意相交误作碰撞；检测是诊断，不自动改画面。跨场景重建必要对象，保持题干、图像及结论一致。清晰变量命名，便于精准微调，不依赖上一个场景的 Python 对象。
## 3. 可选 `board_kit` 辅助工具速查（按需选用，不强求）

你可以直接写原生 Manim 代码，也可以按需调用以下 `animation_engine.code.board_kit` 组件并自由调整参数：
- `board_bounds(watermark_safe_region_px=None, caption_safe_region_px=None) -> dict`：返回 `left_x`、`right_x`、`stem_top_y`、`stem_left_x`、`stem_right_x`、`board_floor_y`、`board_width` 等安全坐标。
- `mixed_text(*parts, font_size=26, math_scale=None, color=INK_BLACK, buff=None) -> VGroup`：横排混排 `("t", "中文")` 与 `("m", r"LaTeX")` 并对齐基线。
- `highlight_clause(self, mobj, *, color=HIGHLIGHT_BLUE, restore_color=INK_BLACK) -> None`（支持传入多个子块如 `highlight_clause(self, c1, c2)` 在同一句内依次扫读点亮）：**必须第 1 参数传 `self` 并直接调用，严禁套入 `self.play(...)`**。
- `board_note(*lines, color=HIGHLIGHT_BLUE, font_size=22, line_buff=0.14) -> VGroup`：无厚底框的轻量黑板旁注/思路提示（细竖线+短句公式），比大卡片更省纵向空间。
- `aside_card(title, *body_lines, kind="knowledge", width=5.0, title_size=24, body_size=22, min_scale=0.80) -> VGroup`：`kind` 仅允许 `"guide"` / `"knowledge"` / `"warning"` / `"summary"`（已内置最低缩放底线 `0.80`）。
- `two_column_frame(left_group, right_group, *, top_y, bottom_y, left_x=-6.50, right_x=6.50, gap=0.50, align_top=False, min_scale=0.80) -> VGroup`：仅双栏布局时选用。
- `fit_stem(stem, bounds, *, max_height=1.85, align_left=False) -> Mobject`：顶栏题干优先视觉居中，仅逼近右上角水印时最小左移避让。
- `fit_into_region(group, *, top_y, bottom_y, left_x=None, right_x=None, center_x=0.0, align_left=False, align_top=False, min_scale=0.80) -> Mobject`：在安全区内定位。
- `math_axes_box(x_range, y_range, *, x_length=4.6, y_length=3.4, x_label="x", y_label="y", font_size=22) -> tuple[Axes, VGroup]`：不支持 `width`/`height`，返回二元组 `(axes, group)`。
- `integral_area_with_sweep(axes, lower_fn, upper_fn, x_range, *, sweep_x=None, lower_label="", upper_label="", fill_color="#BFDBFE", fill_opacity=0.45) -> VGroup`：需要 4 个位置参数，返回 `VGroup`（用 `FadeIn`/`Create` 播放，非 `Animation`）。
- `matrix_chain(matrices, arrows=None, *, max_width=12.2, scale=0.64, h_buff=0.22, v_buff=0.28, color=INK_BLACK) -> VGroup`
- `sign_chart(intervals, top_label, signs, bottom_label="", trends=None, *, col_width=1.85, row_height=0.58, font_size=22) -> VGroup`
- `option_elimination_board(items, *, title="选项辨析与排雷", width=4.9, title_size=24, body_size=22) -> VGroup`
- `mcq_options_grid(options, *, max_width=10.4, font_size=26) -> VGroup`
- `active_pointer(target, *, color=HIGHLIGHT_BLUE, buff=0.14) -> Text`
