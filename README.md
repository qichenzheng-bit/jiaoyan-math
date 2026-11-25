# 微光数学 · 教研工作台

个人考研数学教研与创作系统。视频引擎暂不接入。

## 当前阶段：01.01–01.09 基础代码
前后端、导航、数据库迁移、认证、公共文件服务、数学公式预览、基础设置及部署脚本已提交。具体教研业务与完整数学编辑器尚未开发，CI 和服务器验收仍需验证。

## 本地开发
需要 Python 3.12、Node.js 22、PostgreSQL。先创建专用数据库及非超级用户，配置环境变量 DATABASE_URL（postgresql+psycopg://...）、APP_ORIGIN=http://localhost:5173、COOKIE_SECURE=false（仅本机 HTTP 开发）。生产必须使用 HTTPS 和 COOKIE_SECURE=true。文件服务还需要绝对路径 STORAGE_ROOT。.env.example 仅为配置样例，程序从进程环境读取，不自动加载。

后端（在 backend 目录）：
```sh
python -m venv .venv
# Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m app.admin create
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
管理员密码通过终端隐藏输入，不写入仓库。忘记密码使用 python -m app.admin reset。

前端（在 frontend 目录）：
```sh
npm install
npm run dev
```
访问 http://localhost:5173（须与 APP_ORIGIN 一致）。

## 测试
backend：python -m pytest -q
frontend：npm run build

## 部署
见 deploy/README.md 和 docs/phase-01.md。使用已有 self-hosted Runner，须首次配置服务器及 HTTPS 并启用 ENABLE_DEPLOY。禁止用开发服务器作为公开生产服务。
