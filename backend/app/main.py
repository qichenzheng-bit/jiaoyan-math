import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.api.system import router as system_router
from app.api.auth import router as auth_router
from app.api.files import router as files_router
from app.api.settings import router as settings_router
from app.core.config import settings
from app.api.resources import router as resource_router
from app.api.qoder import router as qoder_router
from app.api.chat import router as chat_router

logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.version,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(system_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(files_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(resource_router, prefix="/api")
    app.include_router(qoder_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Never echo submitted passwords or other input in validation errors.
        return JSONResponse(status_code=422, content={"detail": "请求参数格式或长度不正确"})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error("Database operation failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "数据库暂不可用"})
    from app.web import mount_web
    mount_web(app)
    return app

app = create_app()
