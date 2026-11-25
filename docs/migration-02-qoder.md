# 教学资源迁移第一批及 Qoder CN 实验接入

来源 weiguang-math-V5 @ 849cb7f2dd4fa54aad910bfdb162840a5f713f9d。原样复用 content_normalization.py 和 solution_methods.py，保存原始文本，完全重复仅提示不自动合并。新增独立教学资源表（题目、知识单元、来源资料），不导入旧数据库，不关联视频。手动录入、编辑、搜索、归档、恢复、来源关联、重复提示已实现；知识图谱、批量 PDF、Word、讲义、组卷、聊天记忆等仍待分批迁移。

Qoder CN：调用参考旧仓库 cli_specs 和 command_builder，仅 Auto/Fast 两档实验。网页使用现有管理员鉴权及 Origin 校验，调用本机 Unix socket 独立 worker。worker 不以 Web/Runner 账号或 root 运行，不继承数据库环境；默认关闭工具及会话持久化，临时空目录调用。未安装/授权时显示不可用；不可将 PAT、密码或登录文件上传至仓库。账号登录与 Linux PATH、实际参数必须现场验证。安装见 https://qoder.com.cn/cli ，应以独立账号安装、授权。系统服务模板和 worker 需管理员审阅后安装到 /opt/jiaoyan-qoder、/etc/systemd/system，不能从可写工作目录直接以 root 执行。网页仅单轮同步测试，40 秒超时，不是生产聊天或任务系统。

验收：CI 的 Alembic schema check、PostgreSQL CRUD 与前端构建；服务器先验证资源录入、查重和归档，然后独立账号 CLI 安装登录、启动 worker、网页测试。未验证真实模型调用。
