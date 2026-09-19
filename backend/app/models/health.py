"""Health check history for providers, credentials, models and model endpoints.

Why four nullable foreign keys instead of one polymorphic ``target_id``:

* ``target_type`` + ``target_id`` remain as the portable, generic pointer (and keep
  every M1 row meaningful), but they cannot express a constraint, a cascade or a
  join. The routing engine in M5 has to answer questions like "which credential of
  provider X is rate limited right now?" — with a polymorphic id that is a
  full-table scan and no referential integrity;
* the typed columns give real foreign keys (``ON DELETE SET NULL``) and indexes, so
  deleting a credential does not orphan its health history;
* ``rollup`` health (the current state) lives on the entities themselves
  (``providers.health_status``, ``provider_credentials.status``); this table is the
  observation log that the routing engine will aggregate.

No periodic worker is implemented in M1 — the schema and the write path exist so M5
can add schedulers without a migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import HealthStatus, HealthTargetType, enum_type


class HealthCheck(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "health_checks"

    # --- generic pointer (portable, kept from M1) ---------------------------
    target_type: Mapped[HealthTargetType] = mapped_column(
        enum_type(HealthTargetType, "health_target_type"),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)

    # --- typed targets (referential integrity + joins for the router) -------
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

    # --- observation --------------------------------------------------------
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
