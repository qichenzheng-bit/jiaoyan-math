# 微光数学 · 教研工作台 V1

个人数学教研与创作系统。包含 AI 聊天与工作、手动和智能录入、原始资料库、题库与查重、知识库与知识标签图谱、来源统计、组卷、讲义、教材、排版与 PDF 导出、视频制作、封面、教学作品、Qoder CN 账号与签到、系统设置。内容发布、商品售卖及运营统计不属于 V1 范围。

## 本地开发
生产及 CI 基线 Python 3.10、Node.js 22、PostgreSQL 16（独立视频引擎使用自己的 Python >=3.11 环境）。配置 DATABASE_URL、APP_ORIGIN=http://localhost:5173、COOKIE_SECURE=false（仅本机 HTTP）、绝对路径 STORAGE_ROOT。生产必须使用 HTTPS 和 COOKIE_SECURE=true。程序读取进程环境，不自动加载 .env。
```sh
cd backend
python -m venv .venv
# 激活虚拟环境后
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m app.admin create
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
在另一终端进入 frontend，安装依赖并执行 npm run dev。管理员密码只通过终端隐藏输入；重置使用 python -m app.admin reset。

## 运行与验收
- 原始文件单文件上传上限 200 MiB；完整文档导出数据上限 200 MB。
- 数学公式使用 LaTeX。AI 工作可自动执行非破坏性工具，正式录入、导出和视频审核仍由用户确认。
- 测试：backend 下 python -m pytest -q；frontend 下 npm run build；GitHub Actions 负责自动化、浏览器测试、PDF 和检索基准及部署。
- 生产部署与恢复：[部署说明](deploy/README.md)、[加密仓库备份](docs/business-backup.md)、[视频引擎](docs/video-migration.md)。
- V1 是固定产品版本名称；提交 SHA 用于精确定位实际部署。CI 通过不等于真实模型、视频或数据恢复通过。
