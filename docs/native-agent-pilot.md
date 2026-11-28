# 原生 Agent 试点（阶段一）

- 保留旧引擎与现有用户偏好。Python SDK 原生 session 支持恢复；可配置的自动长期记忆目前须另行评估 TypeScript SDK。
- Worker 15 增加官方 Python SDK + 进程内 MCP。使用原有 Qoder 账号、独立非 root Worker 与 Unix socket；业务回调在应用进程中验证并执行，禁止任意 shell/数据库/宿主文件访问。
- 默认不开启。管理员先从受信任部署目录执行 sudo bash deploy/upgrade-qoder-native-agent.sh；验证 SDK 实际模型、MCP 发现、视觉返回、会话恢复、取消、错误修复后，再在应用环境配置 WG_NATIVE_AGENT=1 并重启应用。不要在生产正式切换前删除旧逻辑。
- 试点：业务查询、非模型依赖的草稿工具、直接图片/PDF页、单文件连续页题目审核草稿。已存在批次不覆盖。第二阶段增加原生Skills、只读数学审核子Agent、Word正文和内嵌图、资料库关联、实际工作进度查询、未审核旧草稿安全重新识别。多个文件可独立创建审核草稿；混合文件跨文件统一草稿、原生自动记忆、视频子任务、原生会话清理与备份、追加要求即时中断及真实模型兼容测试仍待后续。
- Qoder 原生会话由 workspace UUID 隔离工作目录；实际 session ID 保存在工作记录中。需备份 Worker 用户的原生会话目录并验证恢复；不允许把宿主机 Bash/Read 等工具直接开放给用户指令。
- 关闭试点只需去掉 WG_NATIVE_AGENT=1。已有业务草稿保留；当前原生运行任务先停止或结束。

- Worker 15 需要新版 Python SDK 的 AgentDefinition、AssistantMessage、TextBlock 及 MCP ToolAnnotations。官方文档： https://docs.qoder.cn/cli/sdk/references-python 、https://docs.qoder.cn/cli/sdk/mcp 、https://docs.qoder.cn/cli/sdk/skills 。

## 阶段三：聊天模式

- 新增独立试点开关 `WG_NATIVE_CHAT=1`，聊天和工作共用 Worker 原生 SDK、Skills、MCP 及原件读取能力；聊天只读，实际业务写入仍在工作模式。
- 每条原生助手消息持久保存原生会话ID及操作者关联；后续同一聊天使用 resume，只在初次迁移或分支时补入尚未进入原生会话的历史。
- 用户提供的原始附件可直接读取，禁止聊天原件工具读取未关联的文件。
- 旧聊天历史、停止、分支和转工作入口兼容；原生会话本地存储的删除同步、备份与实机恢复验证尚未完成，因此试点保持关闭。
- Python SDK 长期自动记忆仍不支持配置，保留现有用户偏好及教学规范。

## 阶段四：官方会话存储和原生自动记忆

- 官方最新 Memory 文档已新增 Python 原生 `memory` 选项和 `flush_memory()`。旧版本文档/SDK 未必具备；采用实际接口检测，不盲目更换语言。参考 https://docs.qoder.cn/en/cli/sdk/memory 。
- 采用官方 `session_store` 接口，SQLite仅存储 SDK 原始会话条目，不理解或重新生成内容；每个会话独立文件，事务顺序、精确重放去重、子Agent记录隔离。参考 https://docs.qoder.cn/cli/sdk/session-storage 。
- Worker 16 在原生回复完成后等待SDK关闭及记忆flush；检测会话镜像失败与记忆保存异常，不能把模型结束当作已确认记忆写入。
- 应用用户ID绑定工作目录；自动记忆只使用当前用户专属 MEMORY.md，禁用共享CLI用户级记忆。原有显式设置继续保留。若当前SDK无memory字段，不启用自动记忆并报告不可用。
- 会话镜像位于 Worker home 下 .jiaoyan-native-workspaces/<会话ID>/session-mirror.sqlite3；自动记忆在 .jiaoyan-native-memory/<用户ID>/MEMORY.md。需纳入加密备份并做恢复验收；外置删除仅删除镜像，不等价于删除 CLI 本机历史。生产开关继续关闭，直至本机删除同步、备份恢复、SDK联调完成。

### 阶段四验收入口

- `deploy/native-agent-smoke.py --model Auto --vision`：真实SDK、MCP回调、原生会话恢复、可选图片输入。测试使用独立合成数据，消耗实际模型额度，不碰业务数据库，不作为已执行验收。
- `deploy/backup-native-state.sh AGE_PUBLIC_RECIPIENT OUTPUT.age`：管理员离线加密备份，仅覆盖两个应用专属原生目录，不包含CLI认证。需先停止Worker并维持停机，备份后由管理员恢复服务；仍需恢复演练及并入既有自动备份。


### 视频引擎原生接入（Worker 17）
保留原视频引擎固定版本、现有提示词及补充规则、生成/校验/渲染/微调/TTS/审核接口。新的 SDK 视频推理通道只传原始 prompt、system、model、effort，仍使用原流式结果协议，默认关闭。视频任务不加载聊天记忆和额外技能，不运行生成代码；由现有引擎完成渲染校验。原生工作工具可以提交原引擎视频任务，Agent 结束轮次释放共享模型后再轮询生成与自动渲染结果；未成功渲染不得视为完成。
部署后先升级 Worker，真实模型联调、同一题生成与微调回归通过后，管理员在 jiaoyan-qoder.service 的 Environment 中设置 WG_NATIVE_VIDEO=1 并重启空闲 Worker。关闭该变量恢复原 CLI 调用。当前未执行真实模型或渲染验收。

### 阶段六：业务补齐、SDK预检与会话删除同步
- Worker 18 启动时验证 SDK 构造器、MCP、子 Agent、会话存储等实际接口；未通过检查不报告 native_agent 可用。自动记忆仍单独检测，不将其当成实机验证。
- 聊天和工作删除时先确认所属用户、停止任务，再通过专属会话登记清理原生本机 transcript、外置镜像和已登记任务快照；按官方项目目录约定及精确 UUID 匹配，遇到无法确认的路径拒绝清理，保留应用历史。共享长期记忆及旧加密备份不会随单次会话删除。旧试点会话若缺可信登记需管理员处理。
- 新增纯文字审核草稿，继续保留附件原件读取流程，避免AI把转录猜测冒充原文。接入签到/额度/模型及录入状态只读查询。
- 未执行生产删除、SDK实机调用或备份恢复。本机删除目录约定参考 https://docs.qoder.cn/cli/sessions 。

### 实机升级前检查（2026-11-28）
- 官方当前中文版/英文版 Memory 专页仍明确标注自动记忆配置仅 TypeScript 支持；Python 原生会话恢复、外置存储是另一项能力。Python Worker 对可选 memory 字段和 flush_memory 只做能力探测，未发现时不启用；此前阶段四关于 Python 原生自动记忆已普遍支持的说法以此更正。原有明确教学偏好保留。参考 https://docs.qoder.cn/cli/sdk/memory 和 https://docs.qoder.cn/cli/sdk/references-python 。
- 桌面审核测试用 Playwright 自动重试断言等待按钮启用，不取消业务断言。真实 SDK 升级必须在应用新版本发布之后执行；未联调前不启用 WG_NATIVE_AGENT、WG_NATIVE_CHAT、WG_NATIVE_VIDEO。
