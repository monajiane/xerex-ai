"""Xerex AI API application factory.

Two surfaces share this process:

* the public gateway API (``/v1/...``) — milestone M4;
* the admin API (``/api/v1/...``) — milestone M1 onwards.

Everything produced here is English (codes, field names, messages). Persian is a
presentation concern of the admin panel only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.database.redis import close_redis
from app.database.session import dispose_engine
from app.health.state import uptime_seconds
from app.middleware import RequestContextMiddleware
from app.schemas.health import LivenessResponse

logger = get_logger(__name__)

DESCRIPTION = """
Xerex AI is a self-hosted AI management platform: a unified LLM gateway plus an
administration API.

**Language contract** — every identifier, field name, error code and message in
this API is English. The administration panel is Persian-first and RTL, and maps
these stable codes to Persian messages in its own i18n layer.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info(
        "application_starting",
        extra={
            "app": settings.app_name,
            "version": settings.app_version,
            "milestone": settings.milestone,
            "environment": settings.environment,
            "docs_enabled": not settings.is_production,
        },
    )
    try:
        yield
    finally:
        await close_redis()
        await dispose_engine()
        logger.info("application_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        description=DESCRIPTION,
        version=settings.app_version,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-ms"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", response_model=LivenessResponse, tags=["health"])
    async def liveness() -> LivenessResponse:
        """Liveness probe: the process is up (no dependency checks)."""
        return LivenessResponse(
            service=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        )

    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "service": settings.app_name,
                "version": settings.app_version,
                "milestone": settings.milestone,
                "uptime_seconds": uptime_seconds(),
                "health": "/health",
                "api": settings.api_v1_prefix,
            }
        )

    return app


app = create_app()
