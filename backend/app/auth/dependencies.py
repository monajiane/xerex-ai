"""Authentication and authorization dependencies.

RBAC is enforced server side; the Persian admin panel additionally hides
forbidden actions, but never relies on hiding alone (PROMPT.md section 7).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

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


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")
