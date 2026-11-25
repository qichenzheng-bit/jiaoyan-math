# 视频生产迁移第一阶段（独立引擎适配）
源：weiguang-math-V5 @ fec8a4f8c21b829a8f043a2c3538aff4cc48ea08。锁定原始代码而不是重写 Manim、提示词、TTS、渲染、微调、归档。主应用不安装重型依赖。
- 私有 loopback 桥接，服务端 X-API-Key，拒绝重定向及任意外部地址。使用原有登录、Origin 验证。
- 题库题目版本快照 -> 独立引擎 lesson -> generate（原引擎自动校验/渲染）-> render/retry/cancel -> 最新视频、微调及历史 -> 审核批准 -> studio work。只在引擎真实批准后建立作品记录，视频保留在引擎持久目录，支持分段流与下载。暂不支持撤回已归档视频、附图传输或跨服务历史成片导入。
- 跨数据库创建无法组成单事务，先保存本地待绑定项目，遇超时不自动重试；需要管理员核对远端记录后恢复绑定（恢复入口待做）。不得绕开引擎查重。
- 服务器准备（需管理员）：独立低权限账户 jiaoyan-video、独立 PostgreSQL 数据库与用户、独立持久数据目录和备份；使用管理员已授权的只读 GitHub 凭据将锁定源码 checkout 到 /opt/jiaoyan-video/source，确认 git rev-parse HEAD 与 lock 一致；不要将凭据写入仓库或 Runner。安装 Python>=3.11、Manim 所需 Cairo/Pango/pkg-config、FFmpeg、LaTeX、中文字体；独立 venv 安装 animation_engine 与 backend（editable），并安装 av。根据上游真实依赖和 Linux 兼容性验证版本。环境文件填 DATABASE_URL（独立库）、WEIGUANG_API_TOKEN（随机高强度，主应用 VIDEO_ENGINE_TOKEN 与之相同）、存储路径。引擎需真实可用管理员账号，需在原应用配置并测试 generate/edit 模型及 TTS；主应用 Qoder 登录不会自动共享给独立账号。部署示例 service 仅绑定 127.0.0.1；不要公网暴露独立引擎。服务安装、授权与实际渲染尚未执行，须先进行资源容量及安全隔离评估，不能让未经审阅的 AI 代码在主应用账号下运行。
- 该提交实现接入层，不等于源代码物理复制或已安装引擎。只有上游源码 checkout、实际模型生成及完整成片/微调/审核测试全部通过才能称为迁移验收。后续六大导航需在此基础上接入视频制作页。

## 私有源码离线随部署交付
原仓库独立迁移分支 migration/video-engine-fec8a4f 将指定提交的两个运行时源码目录、pyproject 和设计文档打包。目标仓库 vendor/video-engine 包含字节一致的五个分卷及固定 SHA256；CI 与 release.sh 均验证整包并解压到当前 release/video-engine-source。无需在手机终端 git clone 另一个私有仓库，也无需给 Runner 新增私有仓库访问令牌。旧仓库 main 未改变。只复制 Git 已跟踪的运行时源文件，不复制账号凭据、数据库、缓存、历史视频或用户数据。上游旧前端不打包；API 服务找不到静态目录时仅告警。独立服务仍由管理员使用低权限 jiaoyan-video 用户配置；Runner 不获得 root 权限。已安装的 Python/Manim venv 保留。注意：上游连接 URL 需要显式 host 与用户名，安装阶段需使用独立 PostgreSQL 角色及数据库并验证连接，不能直接复用主数据库。Qoder CN 为唯一目标模型，需后续绑定和验证，未授权时不得假装可生成。
