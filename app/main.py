from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.datasets import router as datasets_router
from app.api.health import router as health_router
from app.api.qa import router as qa_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app.name,
        description=settings.app.description,
        version=settings.app.version,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix=settings.app.api_prefix)
    app.include_router(qa_router, prefix=settings.app.api_prefix)
    app.include_router(datasets_router, prefix=settings.app.api_prefix)
    return app


app = create_app()
