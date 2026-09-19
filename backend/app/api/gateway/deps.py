"""Authentication, scopes, rate limits and quotas for the public gateway.

Every check happens here, before a route body runs, and every rejection uses the
OpenAI-compatible error shape (that is what a client library expects). The gateway
never returns Persian text: the error ``code`` is stable and English, and the panel
translates it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.logging import request_id_ctx
from app.models.usage import ApiKey
from app.services.api_keys import ApiKeyService
from app.services.gateway import GatewayFailure
from app.services.rate_limit import gateway_limiter


@dataclass
class GatewayContext:
    """What a gateway route needs: the key, its scopes and who consumed it."""

    api_key: ApiKey
    scopes: tuple[str, ...]
    request_id: str

    def require_scope(self, scope: str) -> None:
        if scope not in self.scopes:
            raise GatewayFailure(
                status_code=403,
                code="insufficient_scope",
                message=f"This API key may not use the '{scope}' capability.",
                error_type="permission_error",
            )


def _presented_key(authorization: str | None, x_api_key: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return x_api_key


async def require_gateway_key(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None,
) -> GatewayContext:
    if not settings.gateway_enabled:
        raise GatewayFailure(
            status_code=503,
            code="gateway_disabled",
            message="The gateway is disabled on this deployment.",
        )

    presented = _presented_key(authorization, x_api_key)
    if not presented:
        raise GatewayFailure(
            status_code=401,
            code="invalid_api_key",
            message="Missing API key. Send it as 'Authorization: Bearer xrx_live_...'.",
            error_type="authentication_error",
        )

    service = ApiKeyService(session)
    api_key = await service.authenticate(presented)
    if api_key is None:
        raise GatewayFailure(
            status_code=401,
            code="invalid_api_key",
            message="The API key is invalid, revoked or expired.",
            error_type="authentication_error",
        )

    limit = api_key.rate_limit_per_min or settings.gateway_default_rate_limit_per_min
    result = await gateway_limiter.hit(
        api_key.prefix, limit=limit, window_seconds=60, kind="api_key"
    )
    if not result.allowed:
        raise GatewayFailure(
            status_code=429,
            code="rate_limit_exceeded",
            message="This API key exceeded its per-minute request limit.",
            error_type="rate_limit_error",
            retry_after_seconds=float(result.retry_after_seconds),
        )

    if await service.quota_exceeded(api_key):
        raise GatewayFailure(
            status_code=429,
            code="quota_exceeded",
            message="This API key exhausted its token quota.",
            error_type="rate_limit_error",
        )

    await service.touch(api_key)
    request_id = request_id_ctx.get() or ""
    return GatewayContext(
        api_key=api_key,
        scopes=tuple(api_key.scopes or ()),
        request_id=request_id,
    )


GatewayContextDep = Annotated[GatewayContext, Depends(require_gateway_key)]


def gateway_session(session: SessionDep) -> AsyncSession:
    """Alias used by routers for readability: the gateway shares the request scope."""
    return session


__all__ = ["GatewayContext", "GatewayContextDep", "gateway_limiter", "require_gateway_key"]
