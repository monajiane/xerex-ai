"""Authentication service: bootstrap, login, refresh rotation and logout.

Route handlers stay thin; all identity logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    AuthenticationError,
    BootstrapClosedError,
    BootstrapDisabledError,
    ConflictError,
    PermissionDeniedError,
    RoleEscalationError,
    SelfRoleChangeError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.enums import AdminRole, AuditAction, UserStatus
from app.models.identity import AdminUser, RefreshToken
from app.repositories.identity import AdminUserRepository, RefreshTokenRepository
from app.services.audit import AuditService

logger = get_logger(__name__)


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    expires_at: datetime
    expires_in: int


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = AdminUserRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.audit = AuditService(session)

    # ------------------------------------------------------------------ #
    # Bootstrap
    # ------------------------------------------------------------------ #
    async def admin_user_count(self) -> int:
        return await self.users.count_all()

    async def requires_bootstrap(self) -> bool:
        return await self.admin_user_count() == 0

    async def bootstrap_allowed(self) -> bool:
        """First-run setup is available only when enabled *and* no owner exists yet."""
        if not settings.bootstrap_enabled_effective:
            return False
        return await self.requires_bootstrap()

    async def bootstrap_owner(
        self,
        *,
        email: str,
        password: str,
        full_name: str | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[AdminUser, SessionTokens]:
        if not settings.bootstrap_enabled_effective:
            raise BootstrapDisabledError()
        if await self.admin_user_count() > 0:
            raise BootstrapClosedError()

        user = AdminUser(
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(password),
            role=AdminRole.OWNER,
            status=UserStatus.ACTIVE,
        )
        await self.users.add(user)
        await self.audit.record(
            AuditAction.BOOTSTRAP_OWNER_CREATED,
            actor=user,
            entity_type="admin_user",
            entity_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        tokens = await self._issue_session(user, ip_address=ip_address, user_agent=user_agent)
        logger.info("bootstrap_owner_created", extra={"admin_user_id": str(user.id)})
        return user, tokens

    # ------------------------------------------------------------------ #
    # Login / refresh / logout
    # ------------------------------------------------------------------ #
    async def authenticate(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[AdminUser, SessionTokens]:
        user = await self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            await self.audit.record(
                AuditAction.LOGIN_FAILED,
                actor_email=email.lower(),
                ip_address=ip_address,
                user_agent=user_agent,
                isolated=True,
            )
            raise AuthenticationError("Invalid email or password.", code="invalid_credentials")
        if user.status != UserStatus.ACTIVE:
            raise PermissionDeniedError("This account is not active.", code="account_inactive")

        user.last_login_at = datetime.now(UTC)
        user.failed_login_count = 0
        await self.session.flush()
        tokens = await self._issue_session(user, ip_address=ip_address, user_agent=user_agent)
        await self.audit.record(
            AuditAction.LOGIN_SUCCEEDED,
            actor=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return user, tokens

    async def refresh(
        self,
        *,
        refresh_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[AdminUser, SessionTokens]:
        payload = decode_token(refresh_token, expected_type="refresh")
        stored = await self.tokens.get_by_hash(hash_token(refresh_token))
        if stored is None or stored.revoked_at is not None:
            raise AuthenticationError("The refresh token is no longer valid.", code="token_revoked")
        if stored.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise AuthenticationError("The refresh token has expired.", code="token_expired")
        if str(stored.jti) != str(payload.get("jti")):
            raise AuthenticationError("The refresh token is invalid.", code="token_invalid")

        user = await self.users.get(stored.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise PermissionDeniedError("This account is not active.", code="account_inactive")

        # Token rotation: the presented refresh token is single-use.
        await self.tokens.revoke(stored)
        tokens = await self._issue_session(user, ip_address=ip_address, user_agent=user_agent)
        await self.audit.record(
            AuditAction.TOKEN_REFRESHED, actor=user, ip_address=ip_address, user_agent=user_agent
        )
        return user, tokens

    async def logout(self, *, refresh_token: str | None, user: AdminUser | None = None) -> None:
        if refresh_token:
            stored = await self.tokens.get_by_hash(hash_token(refresh_token))
            if stored is not None and stored.revoked_at is None:
                await self.tokens.revoke(stored)
        if user is not None:
            await self.audit.record(AuditAction.LOGOUT, actor=user)

    # ------------------------------------------------------------------ #
    # User administration
    # ------------------------------------------------------------------ #
    async def create_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str | None,
        role: AdminRole,
        actor: AdminUser,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUser:
        if len(password) < settings.password_min_length:
            raise ValidationError(
                "The password does not meet the minimum length requirement.",
                code="password_too_short",
                details={"min_length": settings.password_min_length},
            )
        if role == AdminRole.OWNER and actor.role != AdminRole.OWNER:
            # Privilege escalation guard: only an owner may mint another owner.
            raise RoleEscalationError()
        if await self.users.get_by_email(email):
            raise ConflictError("An account with this email already exists.", code="email_taken")
        user = AdminUser(
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
            status=UserStatus.ACTIVE,
        )
        await self.users.add(user)
        await self.audit.record(
            AuditAction.USER_CREATED,
            actor=actor,
            entity_type="admin_user",
            entity_id=user.id,
            diff={"email": user.email, "role": role.value},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return user

    async def update_user(
        self,
        user: AdminUser,
        *,
        changes: dict[str, object],
        actor: AdminUser,
    ) -> AdminUser:
        if user.id == actor.id and changes.get("status") == UserStatus.SUSPENDED:
            raise ValidationError(
                "You cannot suspend your own account.", code="cannot_suspend_self"
            )
        new_role = changes.get("role")
        if new_role is not None:
            if user.id == actor.id:
                # No self-promotion, and no self-demotion either: an administrator's
                # own role is changed by another owner.
                raise SelfRoleChangeError()
            if new_role == AdminRole.OWNER and actor.role != AdminRole.OWNER:
                raise RoleEscalationError()
            if user.role == AdminRole.OWNER and new_role != AdminRole.OWNER:
                raise ValidationError(
                    "The owner role cannot be downgraded.", code="owner_role_protected"
                )
        before = {key: getattr(user, key) for key in changes}
        for key, value in changes.items():
            if value is not None:
                setattr(user, key, value)
        await self.session.flush()
        await self.audit.record(
            AuditAction.USER_UPDATED,
            actor=actor,
            entity_type="admin_user",
            entity_id=user.id,
            diff={
                "before": {k: str(v) for k, v in before.items()},
                "after": {k: str(v) for k, v in changes.items() if v is not None},
            },
        )
        return user

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _issue_session(
        self,
        user: AdminUser,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SessionTokens:
        access = create_access_token(str(user.id), role=user.role.value, email=user.email)
        refresh = create_refresh_token(str(user.id))
        await self.tokens.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_token(refresh.token),
                jti=refresh.jti,
                expires_at=refresh.expires_at,
                ip_address=ip_address,
                user_agent=(user_agent or "")[:400] or None,
            )
        )
        return SessionTokens(
            access_token=access.token,
            refresh_token=refresh.token,
            expires_at=access.expires_at,
            expires_in=settings.access_token_ttl_minutes * 60,
        )
