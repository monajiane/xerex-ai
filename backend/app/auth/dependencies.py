"""Authentication and authorization dependencies.

RBAC is enforced server side; the Persian admin panel additionally hides
forbidden actions, but never relies on hiding alone (PROMPT.md section 7).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from ipaddress import IPv4Address, IPv6Address, ip_address

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.database.session import get_db_session
from app.models.enums import AdminRole, UserStatus
from app.models.identity import AdminUser
from app.repositories.identity import AdminUserRepository

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="AdminAccessToken")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUser:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("An access token is required.", code="authentication_required")
    payload = decode_token(credentials.credentials, expected_type="access")
    subject = payload.get("sub")
    if not subject:
        raise AuthenticationError("The token is invalid.", code="token_invalid")
    try:
        import uuid

        user_id = uuid.UUID(str(subject))
    except ValueError as exc:
        raise AuthenticationError("The token subject is invalid.", code="token_invalid") from exc

    user = await AdminUserRepository(session).get(user_id)
    if user is None:
        raise AuthenticationError("The account no longer exists.", code="account_missing")
    if user.status != UserStatus.ACTIVE:
        raise PermissionDeniedError("This account is not active.", code="account_inactive")
    return user


def require_roles(*roles: AdminRole) -> Callable[[AdminUser], AdminUser]:
    allowed = set(roles)

    async def _dependency(user: AdminUser = Depends(get_current_user)) -> AdminUser:
        if user.role not in allowed:
            raise PermissionDeniedError(
                "Your role does not allow this action.",
                code="insufficient_role",
                details={"required_roles": sorted(role.value for role in allowed)},
            )
        return user

    return _dependency  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Client address resolution
# --------------------------------------------------------------------------- #
#: ``X-Forwarded-For`` is only honoured when the *direct peer* is a configured
#: trusted proxy. A client that talks to the API directly cannot spoof its address
#: by sending the header (PROMPT.md 7 — client IP is an audit/rate-limit input).
def _parse_address(value: str) -> IPv4Address | IPv6Address | None:
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.startswith("["):  # [2001:db8::1]:443
        end = candidate.find("]")
        candidate = candidate[1:end] if end != -1 else candidate[1:]
    elif candidate.count(":") == 1:  # 203.0.113.9:443
        host, _, port = candidate.partition(":")
        if port.isdigit():
            candidate = host
    try:
        return ip_address(candidate)
    except ValueError:
        return None


def _is_trusted(address: IPv4Address | IPv6Address, networks: Iterable[object]) -> bool:
    return any(address in network for network in networks)  # type: ignore[operator]


def resolve_client_ip(
    peer: str | None,
    forwarded_for: str | None,
    trusted_networks: Iterable[object],
) -> str | None:
    """Return the client address, honouring ``X-Forwarded-For`` only behind trusted proxies.

    ``X-Forwarded-For`` is a right-to-left chain of proxies: the right-most entry is
    the proxy closest to us and the left-most is the original client. We walk it
    from the right and stop at the first address that is not a trusted proxy — that
    address is the real client. Everything the client sends on a direct connection
    is ignored outright.
    """
    peer_address = _parse_address(peer) if peer else None
    if peer_address is None:
        return None
    if not _is_trusted(peer_address, trusted_networks) or not forwarded_for:
        return str(peer_address)

    hops = [_parse_address(entry) for entry in forwarded_for.split(",")]
    for hop in reversed(hops):
        if hop is None:
            # A malformed entry means the rest of the chain is not trustworthy, and
            # the peer is the only address we actually know.
            return str(peer_address)
        if not _is_trusted(hop, trusted_networks):
            return str(hop)

    valid = [hop for hop in hops if hop is not None]
    if valid:
        # The whole chain consists of trusted proxies: the left-most entry is the
        # original client as reported by the outermost trusted proxy.
        return str(valid[0])
    return str(peer_address)


def client_ip(request: Request) -> str | None:
    """Resolved client address for audit records and rate limiting."""
    peer = request.client.host if request.client else None
    return resolve_client_ip(
        peer,
        request.headers.get("x-forwarded-for"),
        settings.trusted_networks,
    )


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")
