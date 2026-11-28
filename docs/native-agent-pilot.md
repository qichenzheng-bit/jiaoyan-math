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
