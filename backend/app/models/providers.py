"""Upstream AI providers, their credentials, models and model endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CredentialStatus, ProviderKind, enum_type
from app.models.types import JsonColumn


class Provider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An upstream AI provider, e.g. ``openai``, ``deepseek`` or a custom gateway."""

    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    kind: Mapped[ProviderKind] = mapped_column(
        enum_type(ProviderKind, "provider_kind"), nullable=False
    )
    base_url: Mapped[str] = mapped_column(String(400), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=30_000, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)

    credentials: Mapped[list[ProviderCredential]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    models: Mapped[list[Model]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )


class ProviderCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Encrypted provider secret. Plaintext is never returned by the API."""

    __tablename__ = "provider_credentials"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    key_hint: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[CredentialStatus] = mapped_column(
        enum_type(CredentialStatus, "credential_status"),
        default=CredentialStatus.UNVERIFIED,
        nullable=False,
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))

    provider: Mapped[Provider] = relationship(back_populates="credentials")
    endpoints: Mapped[list[ModelEndpoint]] = relationship(back_populates="credential")


class Model(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A model exposed by a provider."""

    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("provider_id", "name", name="uq_models_provider_id_name"),)

    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160))
    context_window: Mapped[int | None] = mapped_column(Integer)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    input_price_per_1m: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    output_price_per_1m: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    capabilities: Mapped[dict | None] = mapped_column(JsonColumn)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    provider: Mapped[Provider] = relationship(back_populates="models")
    endpoints: Mapped[list[ModelEndpoint]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )


class ModelEndpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Transport details for calling a model on a provider.

    ``credential_id`` binds an endpoint to a *specific* credential instead of the
    provider's default one. It is an independent, nullable association on purpose:

    * one provider can have many credentials, and different endpoints of the same
      model can use different ones (quotas, regions, billing accounts);
    * a credential row can back endpoints of more than one provider (the same
      upstream account reached through two gateways), so the column is deliberately
      **not** constrained to ``credential.provider_id == model.provider_id``;
    * ``None`` means "use the provider's default credential", which keeps M1 data
      and simple setups valid;
    * ``provider_id`` is an optional *override* of the model's home provider, so the
      routing engine can express "Model A, endpoint 3, reached through provider Y",
      which is what makes cross-provider failover and account reuse expressible.

    The secret itself is never duplicated: endpoints only reference
    ``provider_credentials`` rows, which stay encrypted once.
    """

    __tablename__ = "model_endpoints"

    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("models.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("provider_credentials.id", ondelete="SET NULL"),
        index=True,
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("providers.id", ondelete="SET NULL"),
        index=True,
    )
    path: Mapped[str] = mapped_column(String(400), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="POST", nullable=False)
    streaming_supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    param_map: Mapped[dict | None] = mapped_column(JsonColumn)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    model: Mapped[Model] = relationship(back_populates="endpoints")
    credential: Mapped[ProviderCredential | None] = relationship(back_populates="endpoints")
    provider: Mapped[Provider | None] = relationship(foreign_keys=[provider_id])
