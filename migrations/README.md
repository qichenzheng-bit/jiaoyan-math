# 数据库迁移
实际 Alembic 配置和版本文件位于 backend/alembic.ini 与 backend/migrations。进入 backend 后执行 python -m alembic upgrade head。生产升级前须备份，不自动执行 downgrade。
