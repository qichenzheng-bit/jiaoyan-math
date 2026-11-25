from fastapi import FastAPI
from app.api.system import router
from app.core.config import settings

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(router, prefix="/api")
    return app

app = create_app()
