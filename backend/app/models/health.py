"""Health check history for providers, models and model endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import HealthStatus, HealthTargetType, enum_type


class HealthCheck(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "health_checks"

    target_type: Mapped[HealthTargetType] = mapped_column(
        enum_type(HealthTargetType, "health_target_type"),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    status: Mapped[HealthStatus] = mapped_column(
        enum_type(HealthStatus, "health_status"),
        default=HealthStatus.UNKNOWN,
        nullable=False,
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
