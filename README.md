# 微光数学 · 教研工作台

个人考研数学教研与创作系统。视频引擎独立维护，本仓库暂不接入。

## 当前阶段：01.01–01.02
前后端骨架、响应式导航、健康检查。业务模块、登录、数据库及自动部署尚未实现；仅允许本地或受保护的测试环境访问，不可作为生产环境使用。

## 本地启动
需要 Python 3.12、Node.js 22。

后端：
```sh
cd backend
python -m venv .venv
# Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端（另一终端）：
```sh
cd frontend
npm install
npm run dev
```
访问 http://localhost:5173。Vite 将 /api 请求转发至本地 FastAPI。

## 测试
后端：在 backend 下运行 `python -m pytest -q`。
前端：在 frontend 下运行 `npm run build`。

## 开发计划
见 docs/phase-01.md。自动部署须确认服务器 Runner、持久化路径及 HTTPS 后启用。
