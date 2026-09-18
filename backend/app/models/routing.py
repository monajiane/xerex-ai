"""Routing rules evaluated by the smart routing engine (implemented in M5)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RoutingStrategy, enum_type
from app.models.types import JsonColumn


class RoutingRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "routing_rules"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    strategy: Mapped[RoutingStrategy] = mapped_column(
        enum_type(RoutingStrategy, "routing_strategy"),
        default=RoutingStrategy.PRIORITY,
        nullable=False,
    )
    match_conditions: Mapped[dict | None] = mapped_column(JsonColumn)
    target_model_ids: Mapped[list | None] = mapped_column(JsonColumn, default=list)
    fallback_chain: Mapped[list | None] = mapped_column(JsonColumn, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
