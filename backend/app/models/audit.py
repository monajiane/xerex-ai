"""Administrative audit trail: every mutation is recorded."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import AuditAction, enum_type
from app.models.types import JsonColumn


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), index=True, nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[AuditAction] = mapped_column(
        enum_type(AuditAction, "audit_action", length=48),
        nullable=False,
    )
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    diff: Mapped[dict | None] = mapped_column(JsonColumn)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
