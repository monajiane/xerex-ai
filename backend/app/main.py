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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.gateway import router as gateway_router
from app.api.gateway.router import failure_response
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.crypto import key_fingerprint
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.database.redis import close_redis
from app.database.session import dispose_engine
from app.health.state import uptime_seconds
from app.middleware import RequestContextMiddleware
from app.schemas.health import LivenessResponse
from app.services.gateway import GatewayFailure
from app.services.health_admin import scheduler as health_scheduler

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
    # Configuration safety is enforced when Settings is constructed; the warnings
    # (bootstrap explicitly enabled, no Redis auth, debug left on, ...) are surfaced
    # here so operators see them in the startup logs.
    for warning in settings.validate_runtime_security():
        logger.warning("configuration_warning", extra={"detail": warning})
    logger.info(
        "application_starting",
        extra={
            "app": settings.app_name,
            "version": settings.app_version,
            "milestone": settings.milestone,
            "environment": settings.environment,
            "docs_enabled": not settings.is_production,
            "bootstrap_enabled": settings.bootstrap_enabled_effective,
            # Non-reversible fingerprint: lets operators confirm which credential key
            # is active (e.g. before a rotation) without ever logging the key.
            "credentials_key_fingerprint": key_fingerprint(),
            "credentials_key_derived": settings.encryption_key_is_derived,
        },
    )
    # Scheduled provider checks (opt-in via XEREX_HEALTH_SCHEDULER_ENABLED); the same
    # service backs the «اجرای بررسی» button, so manual and scheduled runs agree.
    health_scheduler.start()
    try:
        yield
    finally:
        await health_scheduler.stop()
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
    app.include_router(gateway_router)

    @app.exception_handler(GatewayFailure)
    async def _gateway_failure_handler(_request: Request, exc: GatewayFailure) -> JSONResponse:
        """Gateway failures use the OpenAI error envelope, never the admin envelope."""
        return failure_response(exc, request_id_ctx.get())

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
