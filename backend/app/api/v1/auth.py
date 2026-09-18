"""Authentication endpoints.

Responses are English and machine-readable. The Persian admin panel maps error
codes to Persian messages; no Persian text is produced here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import SessionDep
from app.auth.dependencies import (
    client_ip,
    get_current_user,
    user_agent,
)
from app.auth.service import AuthService, SessionTokens
from app.core.config import settings
from app.core.errors import RateLimitedError
from app.models.identity import AdminUser
from app.schemas.auth import (
    AdminUserRead,
    AuthenticatedSession,
    BootstrapRequest,
    BootstrapStatus,
    LoginRequest,
    TokenPair,
)
from app.schemas.common import MessageResponse
from app.services.rate_limit import login_limiter

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "xerex_refresh_token"
REFRESH_COOKIE_PATH = f"{settings.api_v1_prefix}/auth"


def _set_refresh_cookie(response: Response, tokens: SessionTokens) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=tokens.refresh_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def _token_pair(tokens: SessionTokens) -> TokenPair:
    return TokenPair(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        expires_at=tokens.expires_at,
    )


@router.get("/bootstrap-status", response_model=BootstrapStatus)
async def bootstrap_status(session: SessionDep) -> BootstrapStatus:
    service = AuthService(session)
    count = await service.admin_user_count()
    return BootstrapStatus(
        requires_bootstrap=count == 0,
        bootstrap_enabled=settings.bootstrap_enabled,
        admin_user_count=count,
    )


@router.post("/bootstrap", response_model=AuthenticatedSession, status_code=status.HTTP_201_CREATED)
async def bootstrap(
    payload: BootstrapRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> AuthenticatedSession:
    service = AuthService(session)
    user, tokens = await service.bootstrap_owner(
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    _set_refresh_cookie(response, tokens)
    return AuthenticatedSession(user=AdminUserRead.model_validate(user), tokens=_token_pair(tokens))


@router.post("/login", response_model=AuthenticatedSession)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> AuthenticatedSession:
    ip = client_ip(request) or "unknown"
    limit = await login_limiter.hit(
        f"{ip}:{payload.email.lower()}",
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    if not limit.allowed:
        raise RateLimitedError(
            "Too many login attempts. Try again later.",
            code="login_rate_limited",
            details={"retry_after_seconds": limit.retry_after_seconds},
        )

    service = AuthService(session)
    user, tokens = await service.authenticate(
        email=str(payload.email),
        password=payload.password,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    await login_limiter.reset(f"{ip}:{payload.email.lower()}")
    _set_refresh_cookie(response, tokens)
    return AuthenticatedSession(user=AdminUserRead.model_validate(user), tokens=_token_pair(tokens))


@router.post("/refresh", response_model=AuthenticatedSession)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
) -> AuthenticatedSession:
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        from app.core.errors import AuthenticationError

        raise AuthenticationError("No refresh token was supplied.", code="refresh_token_missing")
    service = AuthService(session)
    user, tokens = await service.refresh(
        refresh_token=token,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    _set_refresh_cookie(response, tokens)
    return AuthenticatedSession(user=AdminUserRead.model_validate(user), tokens=_token_pair(tokens))


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    current_user: AdminUser = Depends(get_current_user),
) -> MessageResponse:
    service = AuthService(session)
    await service.logout(refresh_token=request.cookies.get(REFRESH_COOKIE_NAME), user=current_user)
    _clear_refresh_cookie(response)
    return MessageResponse(status="logged_out")


@router.get("/me", response_model=AdminUserRead)
async def me(current_user: AdminUser = Depends(get_current_user)) -> AdminUserRead:
    return AdminUserRead.model_validate(current_user)
