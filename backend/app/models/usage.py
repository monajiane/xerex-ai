"""Downstream API keys, client requests and per-attempt usage accounting.

The gateway cannot describe reality with a single row per client request: one
client request may fan out into several upstream routing attempts (failover) before
one of them succeeds. The schema therefore separates:

* :class:`ClientRequest` — one row per request received from a consumer: what was
  asked for, how many attempts it took, and the final outcome plus aggregated
  tokens/cost/latency. This is what dashboards and request logs show.
* :class:`UsageRecord` — one row per **upstream routing attempt**: which provider,
  credential, model and endpoint were tried, and the tokens/cost/latency that
  attempt actually produced (where the upstream reported them).
* :class:`UsageDailyRollup` — the pre-aggregated view for fast dashboards.

That separation is what M4 needs; it is introduced now (with indexes and foreign
keys) so the gateway does not require a destructive redesign later.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ClientRequestState, enum_type
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

    requests: Mapped[list[ClientRequest]] = relationship(back_populates="api_key")
    usage_records: Mapped[list[UsageRecord]] = relationship(back_populates="api_key")


class ClientRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One request received from a consumer of the gateway.

    ``state`` plus ``final_*`` describe the outcome; ``attempt_count`` and the
    aggregate columns make the request list readable without joining every attempt.
    """

    __tablename__ = "client_requests"
    __table_args__ = (
        # The request log lists reverse-chronologically and is usually filtered by
        # outcome, so the most selective pair is indexed together (migration 0003).
        Index("ix_client_requests_started_at", "started_at", "state"),
    )

    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), index=True
    )
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), index=True
    )
    requested_model: Mapped[str | None] = mapped_column(String(160))
    streaming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    state: Mapped[ClientRequestState] = mapped_column(
        enum_type(ClientRequestState, "client_request_state"),
        default=ClientRequestState.PENDING,
        nullable=False,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    final_status_code: Mapped[int | None] = mapped_column(Integer)
    final_error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    api_key: Mapped[ApiKey | None] = relationship(back_populates="requests")
    attempts: Mapped[list[UsageRecord]] = relationship(
        back_populates="client_request",
        cascade="all, delete-orphan",
        order_by="UsageRecord.attempt_number",
    )


class UsageRecord(UUIDPrimaryKeyMixin, Base):
    """One upstream routing attempt made while serving a client request.

    ``credential_id`` and ``endpoint_id`` are recorded because the same model can be
    reached through several endpoints and credentials, and cost/rate-limit
    accountability is per credential, not per provider.
    """

    __tablename__ = "usage_records"
    __table_args__ = (
        UniqueConstraint(
            "client_request_id", "attempt_number", name="uq_usage_records_attempt_number"
        ),
        # Every aggregate filters on the window; appending the id keeps the index
        # usable for counting (migration 0003).
        Index("ix_usage_records_created_at", "created_at", "id"),
        # The request log joins the final attempt of each request; the partial index
        # stays small because a request has exactly one final attempt.
        Index(
            "ix_usage_records_final_attempt",
            "client_request_id",
            postgresql_where=text("is_final"),
            sqlite_where=text("is_final"),
        ),
    )

    request_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    client_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("client_requests.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), index=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL"), index=True
    )
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("provider_credentials.id", ondelete="SET NULL"), index=True
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("models.id", ondelete="SET NULL"), index=True
    )
    endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_endpoints.id", ondelete="SET NULL"), index=True
    )

    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    streaming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    client_request: Mapped[ClientRequest | None] = relationship(back_populates="attempts")
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
