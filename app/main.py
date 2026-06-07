from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import agents, assets, companies, documents, health, prompts, qa, search, tags, tasks
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler, unhandled_error_handler
from app.core.logger import setup_logging
from app.core.middleware import ApiResponseMiddleware, RequestIdMiddleware
from app.db.session import close_pool, get_pool, open_pool
from app.services.embeddings import embedding_provider
from app.services.prompts import seed_default_prompts


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    with get_pool().connection() as conn:
        seed_default_prompts(conn)
        conn.commit()
    try:
        yield
    finally:
        close_pool()


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(ApiResponseMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health.router)
    app.include_router(health.api_router, prefix="/api/v1")
    app.include_router(companies.router, prefix="/api/v1")
    app.include_router(tags.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(qa.router, prefix="/api/v1")
    app.include_router(tasks.router, prefix="/api/v1")
    app.include_router(assets.router, prefix="/api/v1")
    app.include_router(prompts.router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")
    return app


app = create_app()


@app.get("/api/v1/system/info")
def system_info():
    settings = get_settings()
    return {
        "app_version": settings.app_version,
        "env": settings.app_env,
        "vector_enabled": True,
        "llm_provider": settings.llm_provider,
        "llm_configured": bool(settings.llm_base_url and settings.llm_api_key),
        "embedding_provider": embedding_provider(),
        "embedding_model": settings.embedding_model,
        "rerank_enabled": settings.rerank_enabled,
        "time": datetime.now(timezone.utc).isoformat(),
    }
