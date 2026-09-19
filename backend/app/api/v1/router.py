"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1 import (
    api_keys,
    audit,
    auth,
    catalog,
    dashboard,
    health,
    models,
    providers,
    routing,
    settings,
    system,
    usage,
    users,
)
from app.auth.dependencies import get_current_user
from app.core.config import settings as app_settings

api_router = APIRouter()


@api_router.get("", tags=["meta"])
async def api_index(_=Depends(get_current_user)) -> dict[str, object]:
    """Index of the admin API surface for the current milestone."""
    return {
        "api_version": "v1",
        "app": app_settings.app_name,
        "app_version": app_settings.app_version,
        "milestone": app_settings.milestone,
        "environment": app_settings.environment,
        "documentation": {
            "openapi": "/openapi.json",
            "docs": "/docs",
            "redoc": "/redoc",
        },
        "modules": [
            {"key": "auth", "prefix": "/api/v1/auth"},
            {"key": "health", "prefix": "/api/v1/health"},
            {"key": "system", "prefix": "/api/v1/system"},
            {"key": "dashboard", "prefix": "/api/v1/dashboard"},
            {"key": "admin_users", "prefix": "/api/v1/admin-users"},
            {"key": "settings", "prefix": "/api/v1/settings"},
            {"key": "audit_logs", "prefix": "/api/v1/audit-logs"},
            {"key": "catalog", "prefix": "/api/v1/catalog"},
            {"key": "providers", "prefix": "/api/v1/providers"},
            {"key": "models", "prefix": "/api/v1/models"},
        ],
    }


api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(system.router)
api_router.include_router(dashboard.router)
api_router.include_router(users.router)
api_router.include_router(settings.router)
api_router.include_router(audit.router)
api_router.include_router(catalog.router)
api_router.include_router(providers.router)
api_router.include_router(models.router)
api_router.include_router(api_keys.router)
api_router.include_router(routing.router)
api_router.include_router(usage.router)
