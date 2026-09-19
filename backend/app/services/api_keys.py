"""Downstream API keys (M4).

Rules that shape this module:

* the plaintext key exists exactly once — at creation time; only the SHA-256 hash
  and the display prefix are stored (:mod:`app.core.security` owns those primitives);
* a key carries scopes, a per-minute rate limit, an optional token quota and an
  optional expiry, and every one of them is enforced server-side;
* revoking is not deleting: a revoked key keeps its usage history, which is exactly
  what an operator needs afterwards.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import generate_api_key, hash_api_key, mask_api_key
from app.models.enums import AuditAction
from app.models.identity import AdminUser
from app.models.usage import ApiKey, UsageRecord
from app.schemas.api_keys import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, ApiKeyUpdate, ApiKeyUsage
from app.services.audit import AuditService

#: Scopes a key may carry. ``chat`` and ``embeddings`` are inference; ``models`` is
#: read-only catalogue access.
KNOWN_SCOPES: tuple[str, ...] = ("chat", "embeddings", "models")
#: Guard rail so one deployment cannot grow an unbounded number of live keys.
MAX_API_KEYS = 200


class ApiKeyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    # -- reads ---------------------------------------------------------------
    async def list(
        self,
        *,
        search: str | None = None,
        enabled: bool | None = None,
        include_revoked: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ApiKeyRead], int]:
        statement = select(ApiKey)
        counter = select(func.count(ApiKey.id))
        if search:
            pattern = f"%{search.lower()}%"
            condition = func.lower(ApiKey.name).like(pattern) | func.lower(ApiKey.prefix).like(
                pattern
            )
            statement = statement.where(condition)
            counter = counter.where(condition)
        if enabled is not None:
            statement = statement.where(ApiKey.enabled.is_(enabled))
            counter = counter.where(ApiKey.enabled.is_(enabled))
        if not include_revoked:
            statement = statement.where(ApiKey.revoked_at.is_(None))
            counter = counter.where(ApiKey.revoked_at.is_(None))

        statement = statement.order_by(ApiKey.created_at.desc()).offset(offset).limit(limit)
        rows = (await self.session.execute(statement)).scalars().all()
        total = int((await self.session.execute(counter)).scalar_one())
        return [self.read(row) for row in rows], total

    async def get(self, key_id: uuid.UUID) -> ApiKey:
        key = await self.session.get(ApiKey, key_id)
        if key is None:
            raise NotFoundError("The API key does not exist.", code="api_key_not_found")
        return key

    @staticmethod
    def read(key: ApiKey) -> ApiKeyRead:
        return ApiKeyRead(
            id=key.id,
            name=key.name,
            prefix=key.prefix,
            masked=mask_api_key(key.prefix),
            scopes=list(key.scopes or []),
            rate_limit_per_min=key.rate_limit_per_min,
            quota_tokens=key.quota_tokens,
            enabled=key.enabled,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            revoked_at=key.revoked_at,
            created_at=key.created_at,
            updated_at=key.updated_at,
        )

    async def usage(self, key_id: uuid.UUID) -> ApiKeyUsage:
        key = await self.get(key_id)
        rows = (
            await self.session.execute(
                select(
                    func.count(UsageRecord.id),
                    func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                    func.coalesce(func.sum(UsageRecord.output_tokens), 0),
                    func.coalesce(func.sum(UsageRecord.total_tokens), 0),
                    func.coalesce(func.sum(UsageRecord.cost), 0),
                    func.coalesce(
                        func.sum(case((UsageRecord.error_code.is_not(None), 1), else_=0)), 0
                    ),
                ).where(UsageRecord.api_key_id == key.id)
            )
        ).one()
        requests, input_tokens, output_tokens, total_tokens, cost, errors = rows
        return ApiKeyUsage(
            api_key_id=key.id,
            requests=int(requests or 0),
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            total_tokens=int(total_tokens or 0),
            cost=float(cost or 0),
            error_count=int(errors or 0),
            last_used_at=key.last_used_at,
            quota_tokens=key.quota_tokens,
            quota_remaining_tokens=(
                max(key.quota_tokens - int(total_tokens or 0), 0)
                if key.quota_tokens is not None
                else None
            ),
        )

    # -- writes --------------------------------------------------------------
    async def create(
        self,
        payload: ApiKeyCreate,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ApiKeyCreated:
        self._validate_scopes(payload.scopes)
        existing = int((await self.session.execute(select(func.count(ApiKey.id)))).scalar_one())
        if existing >= MAX_API_KEYS:
            raise ConflictError(
                "The maximum number of API keys has been reached.", code="api_key_limit_reached"
            )
        full_key, prefix, hashed = generate_api_key()
        key = ApiKey(
            name=payload.name,
            prefix=prefix,
            hash=hashed,
            scopes=list(payload.scopes or KNOWN_SCOPES),
            rate_limit_per_min=payload.rate_limit_per_min,
            quota_tokens=payload.quota_tokens,
            enabled=True,
            expires_at=payload.expires_at,
            created_by=actor.id if actor else None,
        )
        self.session.add(key)
        await self.session.flush()
        await self.audit.record(
            AuditAction.API_KEY_CREATED,
            actor=actor,
            entity_type="api_key",
            entity_id=str(key.id),
            diff={
                "name": key.name,
                "prefix": key.prefix,
                "scopes": list(key.scopes or []),
                "rate_limit_per_min": key.rate_limit_per_min,
                "quota_tokens": key.quota_tokens,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        read = self.read(key)
        return ApiKeyCreated(**read.model_dump(), secret=full_key)

    async def update(
        self,
        key_id: uuid.UUID,
        payload: ApiKeyUpdate,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ApiKeyRead:
        key = await self.get(key_id)
        changes: dict[str, Any] = {}
        for field in ("name", "rate_limit_per_min", "quota_tokens", "enabled", "expires_at"):
            if field not in payload.model_fields_set:
                continue
            value = getattr(payload, field)
            if getattr(key, field) != value:
                changes[field] = {"from": _jsonable(getattr(key, field)), "to": _jsonable(value)}
                setattr(key, field, value)
        if payload.scopes is not None:
            self._validate_scopes(payload.scopes)
            if list(key.scopes or []) != list(payload.scopes):
                changes["scopes"] = {"from": list(key.scopes or []), "to": list(payload.scopes)}
                key.scopes = list(payload.scopes)
        if changes:
            await self.session.flush()
            await self.audit.record(
                AuditAction.API_KEY_UPDATED,
                actor=actor,
                entity_type="api_key",
                entity_id=str(key.id),
                diff=changes,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return self.read(key)

    async def revoke(
        self,
        key_id: uuid.UUID,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ApiKeyRead:
        key = await self.get(key_id)
        if key.revoked_at is None:
            key.revoked_at = datetime.now(UTC)
            key.enabled = False
            await self.session.flush()
            await self.audit.record(
                AuditAction.API_KEY_REVOKED,
                actor=actor,
                entity_type="api_key",
                entity_id=str(key.id),
                diff={"name": key.name, "prefix": key.prefix},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return self.read(key)

    async def delete(
        self,
        key_id: uuid.UUID,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        key = await self.get(key_id)
        await self.audit.record(
            AuditAction.API_KEY_DELETED,
            actor=actor,
            entity_type="api_key",
            entity_id=str(key.id),
            diff={"name": key.name, "prefix": key.prefix},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.session.delete(key)
        await self.session.flush()

    # -- gateway authentication ---------------------------------------------
    async def authenticate(self, presented_key: str) -> ApiKey | None:
        """Resolve a presented ``xrx_live_...`` key, or ``None`` when unusable.

        The lookup is by hash, and the reason for a rejection is *not* revealed to
        the caller: the gateway answers one generic ``invalid_api_key`` error.
        """
        if not presented_key.startswith("xrx_live"):
            return None
        hashed = hash_api_key(presented_key)
        result = await self.session.execute(select(ApiKey).where(ApiKey.hash == hashed))
        key = result.scalars().first()
        if key is None or not key.enabled or key.revoked_at is not None:
            return None
        if key.expires_at is not None and key.expires_at <= datetime.now(UTC):
            return None
        return key

    async def touch(self, key: ApiKey) -> None:
        key.last_used_at = datetime.now(UTC)
        await self.session.flush()

    async def quota_exceeded(self, key: ApiKey) -> bool:
        if key.quota_tokens is None:
            return False
        consumed = int(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(UsageRecord.total_tokens), 0)).where(
                        UsageRecord.api_key_id == key.id
                    )
                )
            ).scalar_one()
        )
        return consumed >= key.quota_tokens

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _validate_scopes(scopes: list[str] | None) -> None:
        if not scopes:
            return
        unknown = [scope for scope in scopes if scope not in KNOWN_SCOPES]
        if unknown:
            raise ValidationError(
                "One or more scopes are not supported.",
                code="unknown_api_key_scope",
                details={"unknown": unknown, "allowed": list(KNOWN_SCOPES)},
            )


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


__all__ = ["KNOWN_SCOPES", "ApiKeyService"]
