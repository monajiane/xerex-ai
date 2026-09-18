"""Audit trail service. Every administrative mutation is recorded."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_ctx
from app.database.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import AuditAction
from app.models.identity import AdminUser
from app.repositories.platform import AuditLogRepository


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = AuditLogRepository(session)

    async def record(
        self,
        action: AuditAction,
        *,
        actor: AdminUser | None = None,
        actor_email: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        diff: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        isolated: bool = False,
    ) -> AuditLog:
        """Write an audit entry.

        ``isolated=True`` commits the entry in its own transaction. Use it for
        security events on failure paths (e.g. rejected logins) that would
        otherwise be discarded when the request transaction rolls back.
        """
        entry = AuditLog(
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else actor_email,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            diff=diff,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id_ctx.get(),
        )
        if isolated:
            async with session_scope() as detached:
                detached_entry = AuditLog(
                    actor_id=entry.actor_id,
                    actor_email=entry.actor_email,
                    action=entry.action,
                    entity_type=entry.entity_type,
                    entity_id=entry.entity_id,
                    diff=entry.diff,
                    ip_address=entry.ip_address,
                    user_agent=entry.user_agent,
                    request_id=entry.request_id,
                )
                detached.add(detached_entry)
                await detached.flush()
                return detached_entry
        return await self.repository.add(entry)
