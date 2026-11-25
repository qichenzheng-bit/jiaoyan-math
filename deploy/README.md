# 华为云部署
既有 jiaoyan 用户及 GitHub self-hosted Linux/x64 Runner 不必重新安装。默认 Ubuntu 22.04 Python 3.10 可运行当前代码；CI 后续补充 3.10 验证。部署采用 systemd 用户服务 + PostgreSQL 本地 peer 认证 + Nginx HTTPS，不使用 Docker。Runner 不需要 root 或新增 sudo 权限。

1. 在服务器可信仓库副本执行 sudo bash deploy/bootstrap.sh https://实际域名。先核实 jiaoyan 数据库没有被其他服务使用；配置脚本拒绝覆盖已存在的 app.env。安装依赖需联网。配置文件只在服务器上。
2. 配置域名解析、有效 TLS 证书和 nginx.conf.example，执行 nginx -t 后 reload。不得以公开 HTTP 传输账号密码。后端仅监听 127.0.0.1:8765。
3. GitHub Settings > Secrets and variables > Actions > Variables 新建 ENABLE_DEPLOY=true。main 分支提交自动触发 Server CI and release，也可手动运行。通过同服务器隔离测试、前端编译及浏览器测试后才执行部署。Hosted CI 保留供 PR / 手动测试，不消耗每次 main 提交的托管执行器额度。
4. 首次部署后，以 jiaoyan 用户在服务器执行：
   cd ~/jiaoyan-app/current/backend
   set -a; source ~/jiaoyan-app/config/app.env; set +a
   ../venv/bin/python -m app.admin create
5. 在浏览器访问实际 HTTPS 地址。检查 /api/ready、登录、文件上传、公式及设置。

发布前先构建，停服务后协调备份数据库和文件，再执行迁移。健康检查失败且数据库版本不变时尝试恢复上一版本；数据库版本变化时停止服务并保留备份，禁止自动覆盖用户数据。备份位于 ~/jiaoyan-app/backups，包含数据库 dump、文件 tar.gz、原 schema 与旧 release 指针。恢复需先停服务，在独立数据库和目录验证备份，再由管理员明确选择恢复；目前未提供自动恢复命令。备份需定期转存到其他存储、设置保留策略并人工检查剩余空间。未配置 HTTPS、未验证真实服务器前不算通过部署验收。

## 首次验收检查
Actions > Server preflight 可读取 Runner、磁盘、数据库连通性、systemd 及本地健康状态。该流程不打印配置内容或密钥，不安装软件，不启动服务。PENDING 并非通过。CI 增加部署脚本语法检查及 PostgreSQL 文件/设置接口集成测试。备份在迁移前通过 pg_restore --list 和 tar -tzf 检查可读性，但这不等价于实际恢复演练。

## 托管 Runner 未分配时
主分支使用既有非 root 自托管 Runner 串行验证。临时 PostgreSQL 在 /tmp 私有 Unix socket 运行，与正式数据库分离；不读取 app.env、不调用真实 Qoder。仅使用服务器现有 Python 版本，Hosted CI 保留 3.10/3.12 矩阵。Playwright 使用本地缓存，若提示系统依赖不足，由管理员安装所提示的 Chromium 依赖（不得给 Runner sudo 权限）。任何测试失败均不进入 release.sh。截图上传失败不影响已验证的部署结果。自托管 Runner 仅用于可信 main，禁止不可信 PR 执行。
