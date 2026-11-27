# 原生 Agent 试点（阶段一）

- 保留旧引擎与现有用户偏好。Python SDK 原生 session 支持恢复；可配置的自动长期记忆目前须另行评估 TypeScript SDK。
- Worker 14 增加官方 Python SDK + 进程内 MCP。使用原有 Qoder 账号、独立非 root Worker 与 Unix socket；业务回调在应用进程中验证并执行，禁止任意 shell/数据库/宿主文件访问。
- 默认不开启。管理员先从受信任部署目录执行 sudo bash deploy/upgrade-qoder-native-agent.sh；验证 SDK 实际模型、MCP 发现、视觉返回、会话恢复、取消、错误修复后，再在应用环境配置 WG_NATIVE_AGENT=1 并重启应用。不要在生产正式切换前删除旧逻辑。
- 试点：业务查询、非模型依赖的草稿工具、直接图片/PDF页、单文件连续页题目审核草稿。已存在批次不覆盖。Word图片、多文件统一草稿、原生自动记忆、视频子任务、原生会话清理与备份策略、追加要求即时中断、所有模型真实兼容测试仍待后续。
- Qoder 原生会话由 workspace UUID 隔离工作目录；实际 session ID 保存在工作记录中。需备份 Worker 用户的原生会话目录并验证恢复；不允许把宿主机 Bash/Read 等工具直接开放给用户指令。
- 关闭试点只需去掉 WG_NATIVE_AGENT=1。已有业务草稿保留；当前原生运行任务先停止或结束。
