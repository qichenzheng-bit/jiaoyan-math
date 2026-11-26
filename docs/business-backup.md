# 业务数据异地备份（第一阶段）

目标仓库：qichenzheng-bit/jiaoyan-data，main，保持 Private。每天北京时间次日 00:00（即前日24:00），systemd 持久化定时器在错过时间时补跑。失败间隔5分钟，正常情况下最多3次启动/小时。独立低优先级服务，复用现有 Python/psycopg。无须打开网页。使用部署锁，避免与数据库迁移并行；备份不停止 Web 服务。

## 一次性配置（管理员本机及服务器；切勿把私钥发到聊天或仓库）

1. 在可信的离线管理设备安装 age，执行 `age-keygen -o jiaoyan-recovery.agekey`。离线保存私钥和至少一份独立副本，仅将输出的 age1 开头公钥（recipient）配置到服务器。
2. 在服务器安装系统 age 包（Ubuntu: `sudo apt-get install age`，已有则不安装）。以 jiaoyan 用户生成独立 SSH 部署密钥：`ssh-keygen -t ed25519 -f ~/jiaoyan-app/config/backup-deploy-key -N '' -C jiaoyan-backup`。在数据私有仓库 Settings → Deploy keys 中只添加 .pub 公钥，勾选 Allow write access。不要给公开代码仓库写权限。
3. 独立建立已验证的 GitHub SSH known_hosts 文件，核对 GitHub 官方 SSH 指纹后保存于 ~/jiaoyan-app/config/backup-known-hosts。严禁关闭 StrictHostKeyChecking。官方指纹：https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints 。
4. 以 jiaoyan 用户创建 ~/jiaoyan-app/config/backup.json（权限0600）。示例：
```json
{"recipient":"age1...真实公钥","ssh_key":"~/jiaoyan-app/config/backup-deploy-key","known_hosts":"~/jiaoyan-app/config/backup-known-hosts"}
```
5. 在代码部署成功后，以 jiaoyan 用户执行 `bash ~/jiaoyan-app/current/deploy/enable-backup.sh`。首次上传及远端提交验证成功后才启用定时器。网页「系统设置 → 数据与存储」支持查看状态及提交立即备份。查看 `systemctl --user status jiaoyan-backup.timer`，手动备份 `systemctl --user start jiaoyan-backup.service`。失败详情（脱敏）位于 ~/jiaoyan-app/backup-state/status.json；最后成功记录独立保存。
6. 如果系统尚未配置 linger，以管理员确认 `loginctl show-user jiaoyan -p Linger`；本项目 bootstrap 已设置。

## 格式与边界

PostgreSQL 同一 REPEATABLE READ 只读快照内导出 pre/post schema 和分类 CSV，所有导出文件先 gzip 压缩，再经过 age 公钥加密。按内容散列只重加密变化条目，未变化的密文复用并校验；大密文32MiB分片。Git 一次提交原子发布清单及所有文件，推送后核对远端分支。私有本地索引仅保留散列与公开接收者，不存明文。没有变化时不提交。删除条目只移除当前清单里的对应密文，Git 历史仍保留。目录中不含源文件名称（附件仅使用 UUID）。每次扫描登记附件，确保文件大小与 SHA256 正确；归档附件同样备份。不包含未登记文件、视频成片、缓存及运行依赖。数据库中的 users / sessions 只备份表结构，审核记录匿名化；settings 仅允许已知非敏感键；签到历史过滤且恢复后自动领取关闭。业务正文可能含人工粘贴的敏感信息，始终加密；禁止将凭据写入业务正文。

当前明确支持教研主数据库及其附件。独立视频引擎的内部数据库、Manim 源码、微调历史、成片尚未接入；现有 video_projects 元数据已备份。尚未实现的 AI 记忆、商品数据等目录仍为空。新增数据表或未识别资源类型将使备份失败，必须更新分类映射并验收。Git 仓库不适合无限增长的大量二进制；需监控容量，后续可迁移对象存储。临时明文只在服务器私有 staging 目录，正常退出删除；异常断电可能残留，管理员应在服务停止后安全清理 backup-state/run-*，不要删除配置或 index.json。禁止在不可信的公开仓库 PR 上运行生产 Runner；建议进一步将备份凭据隔离到独立服务账号/私有部署 Runner。

## 恢复演练（不覆盖生产）

选择私有仓库的备份提交，在可信恢复机器 clone/checkout。离线 age 私钥只用于恢复机器。使用现有 Python 环境（psycopg）以及 age、psql、PostgreSQL，先由数据库管理员创建空数据库（名称必须为 jiaoyan_restore_开头）。使用有权限的本地 PostgreSQL 用户执行：
```sh
python deploy/backup.py restore --repo /绝对路径/jiaoyan-data --identity /离线位置/jiaoyan-recovery.agekey --database jiaoyan_restore_test --files /绝对路径/尚不存在的恢复附件目录
```
脚本核验密文、逐项 age 认证解密，先创建结构，再恢复分类数据，核验附件及数据库约束。禁止覆盖生产库。失败时目标库可能是部分恢复状态，管理员应丢弃演练目标并重新创建空库（不要删除生产库）。恢复后需重新创建管理员、登录 AI 并配置服务凭据，再逐项核验业务与应用迁移版本；正式切换需另行批准。此代码未代替真实恢复演练，必须实际验证后才认定可恢复。

更新密钥时必须保留旧私钥用于历史版本。当前不自动清除历史备份，也不自动上传加密私钥。生产迁移前备份只在配置完成后启用；如果备份失败则拒绝继续迁移，不影响无结构变动的普通代码发布。
