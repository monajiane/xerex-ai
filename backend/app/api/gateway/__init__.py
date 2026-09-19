"""Public gateway surface (``/v1``)."""

from app.api.gateway.deps import GatewayContext, require_gateway_key
from app.api.gateway.router import router

__all__ = ["GatewayContext", "require_gateway_key", "router"]
