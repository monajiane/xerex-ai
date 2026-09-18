"""Reference catalogs.

These endpoints expose *real* static metadata — the provider kinds the platform
supports and the routing strategies it will implement — so the Persian admin
panel can build its forms and clearly marked placeholders without inventing data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.models.identity import AdminUser
from app.providers import registry as provider_registry
from app.router import engine as routing_engine

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/providers")
async def provider_catalog(_: AdminUser = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "items": provider_registry.catalog(),
        "implemented": False,
        "milestone": "M2",
    }


@router.get("/routing-strategies")
async def routing_strategies(_: AdminUser = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "items": routing_engine.catalog(),
        "implemented": False,
        "milestone": "M5",
    }
