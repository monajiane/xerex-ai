"""Downstream API keys and usage accounting."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import JsonColumn


class ApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A downstream ``xrx_live_...`` key issued to an API consumer.

    Only the hash and a display prefix are stored; the full key is shown once at
    creation time.
    """

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    scopes: Mapped[list | None] = mapped_column(JsonColumn, default=list)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    quota_tokens: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL")
    )

    usage_records: Mapped[list[UsageRecord]] = relationship(back_populates="api_key")


class UsageRecord(UUIDPrimaryKeyMixin, Base):
    """One upstream request, recorded by the gateway."""

    __tablename__ = "usage_records"

    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), index=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL"), index=True
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("models.id", ondelete="SET NULL"), index=True
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    streaming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )

    api_key: Mapped[ApiKey | None] = relationship(back_populates="usage_records")


class UsageDailyRollup(UUIDPrimaryKeyMixin, Base):
    """Pre-aggregated usage for fast dashboards and CSV exports."""

    __tablename__ = "usage_daily_rollups"
    __table_args__ = (
        UniqueConstraint(
            "day", "provider_id", "model_id", "api_key_id", name="uq_usage_rollup_dimensions"
        ),
    )

    day: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE")
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("models.id", ondelete="CASCADE")
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_keys.id", ondelete="CASCADE")
    )
    requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0, nullable=False)
    p95_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0, nullable=False)
