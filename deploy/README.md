# 华为云部署
既有 jiaoyan 用户及 GitHub self-hosted Linux/x64 Runner 不必重新安装。默认 Ubuntu 22.04 Python 3.10 可运行当前代码；CI 后续补充 3.10 验证。部署采用 systemd 用户服务 + PostgreSQL 本地 peer 认证 + Nginx HTTPS，不使用 Docker。Runner 不需要 root 或新增 sudo 权限。

1. 在服务器可信仓库副本执行 sudo bash deploy/bootstrap.sh https://实际域名。先核实 jiaoyan 数据库没有被其他服务使用；配置脚本拒绝覆盖已存在的 app.env。安装依赖需联网。配置文件只在服务器上。
2. 配置域名解析、有效 TLS 证书和 nginx.conf.example，执行 nginx -t 后 reload。不得以公开 HTTP 传输账号密码。后端仅监听 127.0.0.1:8765。
3. GitHub Settings > Secrets and variables > Actions > Variables 新建 ENABLE_DEPLOY=true。main 分支提交自动触发 CI and release。托管执行器完成 Python 3.10/3.12、前端编译、脚本检查及浏览器验收后，才允许可信 main 进入现有服务器部署。Server CI and release 保留为手动备用流程，不与主流程重复触发。
4. 首次部署后，以 jiaoyan 用户在服务器执行：
   cd ~/jiaoyan-app/current/backend
   set -a; source ~/jiaoyan-app/config/app.env; set +a
   ../venv/bin/python -m app.admin create
5. 在浏览器访问实际 HTTPS 地址。检查 /api/ready、登录、文件上传、公式及设置。

按管理员要求停用本地部署备份，每次部署在锁内清空 ~/jiaoyan-app/backups 专用目录，不删除正式数据库、上传文件、配置或程序。迁移前检查数据库连通性。健康检查失败且数据库版本不变时尝试恢复上一代码版本；数据库版本变化时停止服务并等待管理员处理。没有本地备份可用于数据库或文件恢复，请明确知悉数据丢失风险。

## 首次验收检查
Actions > Server preflight 可读取 Runner、磁盘、数据库连通性、systemd 及本地健康状态。该流程不打印配置内容或密钥，不安装软件，不启动服务。PENDING 并非通过。CI 增加部署脚本语法检查及 PostgreSQL 文件/设置接口集成测试。部署不再生成数据库和文件备份。

## 托管 Runner 未分配时
主分支使用既有非 root 自托管 Runner 串行验证。临时 PostgreSQL 在 /tmp 私有 Unix socket 运行，与正式数据库分离；不读取 app.env、不调用真实 Qoder。仅使用服务器现有 Python 版本，Hosted CI 保留 3.10/3.12 矩阵。Playwright 使用本地缓存，若提示系统依赖不足，由管理员安装所提示的 Chromium 依赖（不得给 Runner sudo 权限）。任何测试失败均不进入 release.sh。截图上传失败不影响已验证的部署结果。自托管 Runner 仅用于可信 main，禁止不可信 PR 执行。

公开仓库请严格审核外部 PR，禁止不可信工作流使用生产自托管 Runner；建议将生产部署 Runner 放在仅维护者可访问的私有部署仓库，避免公开仓库 PR 工作流攻击。不要在公开仓库或日志中存放生产密钥。


## Qoder CN 实时积分执行服务升级
普通 Web 自动部署不会也不应覆盖独立服务的 root 持有代码。因此页面出现旧版本提示时，管理员应从已审阅的可信仓库版本执行（先确保没有正在运行的 AI 或视频任务）：

```sh
sudo bash deploy/upgrade-qoder-usage.sh
```

脚本验证官方 SDK 提供 get_usage_info、检查旧服务状态、更新 worker 并重启，检查 V12+ 与 usage_discovery；失败恢复旧 worker。不会删除 CLI 登录数据，也不需要重新输入 PAT。若 SDK 不兼容，先由管理员审阅并在独立 SDK 环境中升级官方 qodercn-agent-sdk（该环境不属于 Web 服务）；若 CLI 不支持 get_usage_info，还需按官方方法升级 CLI。升级后在 AI 账号或签到页面点击刷新积分，以实际返回的额度包为准。

签到助手保留 Qoder CN 官方领取渠道和手工历史记录。原 V5 使用 PAT 及未公开桌面活动接口自动领取；现行官方活动说明限定桌面端、移动端与 IDE，未公开支持服务器自动领取的接口。实验适配器仅尝试用户明确授权的 PAT，不提取桌面凭据、不伪造客户端或设备身份、不绕过平台拒绝。


## Qoder CN 签到助手（实验性 PAT 适配）
参考原 V5 qiandao 模块及公开项目 G57651/dsh-dual-checkin、dingminhua/dsh-connect-qoder 的状态优先和轮次逻辑。仅支持一个本人 CN 账号，不与 AI CLI 登录或旧手工别名历史自动绑定。自动领取默认关闭，平台若拒绝或未提供明确活动，不视为成功。官方规则：https://docs.qoder.cn/events/100credits 。建议优先使用官方领取渠道。

从本人 Qoder CN 账号设置创建 PAT。部署新版本后，打开微光数学的「签到助手 → 账号设置」，粘贴 PAT 并点击「验证并保存」。无需登录服务器终端。保存前验证 PAT 授权，使用 0600 权限文件原子写入服务器配置目录，令牌不回显、不写数据库、不进入 GitHub 或日志。PAT 与 AI CLI 登录独立。更换凭据关闭自动领取、建立新余额基线，旧历史保留在内部归档中；当前页面不混合不同凭据的数据。

后台每分钟查询 PAT 所属账号的实际额度包，网页每 30 秒读取后台状态。积分流水记录相邻可比较快照的净变化（非官方交易明细），不把余额增加直接标记为签到，也不把减少全部解释成模型消耗。首个快照及额度包集合改变时只建立基线。每日增减按北京时间统计，保留最近 200 条余额变化记录。原 AI SDK 实时积分保留为独立折叠区域。

先点击立即领取，查看真实平台结果；符合条件且平台允许时，再自行开启自动领取。后台北京时间 10:05 起检查本轮，网络异常间隔 15 分钟最多尝试三次。删除 PAT 会关闭自动领取；应同时在官方账号管理撤销不再使用的 PAT。无需更新已验证的独立积分 worker。
