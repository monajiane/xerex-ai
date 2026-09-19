"""Provider / credential / model contracts.

These schemas are the frozen API contract for milestone M2–M3. They are defined
now so the Persian admin panel can be built against a stable shape without being
rewritten later; the endpoints that consume them land with those milestones.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, HttpUrl

from app.models.enums import CredentialStatus, HealthStatus, ProviderKind
from app.schemas.common import ApiModel, TimestampedRead


class ProviderBase(ApiModel):
    name: str = Field(max_length=120)
    kind: ProviderKind
    base_url: HttpUrl
    description: str | None = Field(default=None, max_length=1000)
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10_000)
    weight: int = Field(default=100, ge=0, le=10_000)
    timeout_ms: int = Field(default=30_000, ge=1_000, le=600_000)
    max_retries: int = Field(default=2, ge=0, le=10)


class ProviderCreate(ProviderBase):
    slug: str | None = Field(default=None, max_length=80)


class ProviderUpdate(ApiModel):
    name: str | None = None
    base_url: HttpUrl | None = None
    description: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    weight: int | None = None
    timeout_ms: int | None = None
    max_retries: int | None = None


class ProviderRead(ProviderBase, TimestampedRead):
    id: uuid.UUID
    slug: str
    health_status: HealthStatus = HealthStatus.UNKNOWN
    credential_count: int = 0
    model_count: int = 0


class CredentialCreate(ApiModel):
    label: str = Field(max_length=120)
    secret: str = Field(min_length=8, max_length=4096)


class CredentialRead(TimestampedRead):
    id: uuid.UUID
    provider_id: uuid.UUID
    label: str
    status: CredentialStatus
    key_hint: str = Field(description="Masked display hint, never the secret itself.")
    last_verified_at: datetime | None = None
    last_error_code: str | None = None
    created_at: datetime


class ModelBase(ApiModel):
    name: str = Field(max_length=160)
    display_name: str | None = Field(default=None, max_length=160)
    context_window: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    input_price_per_1m: float | None = Field(default=None, ge=0)
    output_price_per_1m: float | None = Field(default=None, ge=0)
    capabilities: dict | None = None
    enabled: bool = True


class ModelRead(ModelBase, TimestampedRead):
    id: uuid.UUID
    provider_id: uuid.UUID
    deprecated: bool = False
    discovered_at: datetime | None = None


class ModelEndpointRead(TimestampedRead):
    id: uuid.UUID
    model_id: uuid.UUID
    #: Explicit dispatch target: the endpoint decides which provider and which
    #: credential a request leaves through (pre-M2 correction, item 8).
    provider_id: uuid.UUID | None = None
    credential_id: uuid.UUID | None = None
    path: str
    method: str
    streaming_supported: bool
    param_map: dict | None = None
    enabled: bool


class ModelDiscoveryRequest(ApiModel):
    provider_id: uuid.UUID
    overwrite_existing: bool = False


class ModelDiscoveryResult(ApiModel):
    provider_id: uuid.UUID
    discovered: int
    created: int
    updated: int
    models: list[ModelRead] = []


class ModelTestRequest(ApiModel):
    model_id: uuid.UUID
    prompt: str = Field(min_length=1, max_length=8000)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=256, ge=1, le=8192)
    stream: bool = False


class ModelTestResult(ApiModel):
    model_id: uuid.UUID
    provider_id: uuid.UUID
    latency_ms: int
    input_tokens: int
    output_tokens: int
    output_text: str
    finish_reason: str | None = None
    error_code: str | None = None


# --------------------------------------------------------------------------- #
# M2 — provider & credential administration
# --------------------------------------------------------------------------- #
class ProviderTestResult(ApiModel):
    """Outcome of "آزمایش اتصال" / credential verification.

    ``ok=False`` always carries a stable ``error_code`` so the Persian UI can
    explain the failure without parsing English text.
    """

    provider_id: uuid.UUID
    credential_id: uuid.UUID | None = None
    ok: bool
    latency_ms: int
    status_code: int | None = None
    error_code: str | None = None
    detail: str | None = None
    model_count: int | None = None


class CredentialUpdate(ApiModel):
    label: str | None = Field(default=None, max_length=120)
    status: CredentialStatus | None = None


class CredentialRotateRequest(ApiModel):
    secret: str = Field(min_length=8, max_length=4096)


class ProviderDeleteImpact(ApiModel):
    """What a delete would remove, shown in the Persian confirmation dialog."""

    provider_id: uuid.UUID
    name: str
    credential_count: int
    model_count: int
    endpoint_count: int


# --------------------------------------------------------------------------- #
# M3 — model registry, discovery and playground
# --------------------------------------------------------------------------- #
class ModelWrite(ApiModel):
    """Fields an administrator may set on a model."""

    display_name: str | None = Field(default=None, max_length=160)
    context_window: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    input_price_per_1m: float | None = Field(default=None, ge=0)
    output_price_per_1m: float | None = Field(default=None, ge=0)
    capabilities: dict | None = None
    enabled: bool | None = None
    deprecated: bool | None = None


class ModelCreate(ModelWrite):
    provider_id: uuid.UUID
    name: str = Field(max_length=160)
    display_name: str | None = Field(default=None, max_length=160)


class ModelDiscoveryResultDetail(ModelDiscoveryResult):
    """Discovery outcome plus what changed, so the panel can explain it."""

    skipped: int = 0
    failed: int = 0
    provider_name: str


class ModelEndpointCreate(ApiModel):
    path: str = Field(max_length=400)
    method: str = Field(default="POST", max_length=10)
    streaming_supported: bool = True
    param_map: dict | None = None
    enabled: bool = True
    credential_id: uuid.UUID | None = None


class ModelEndpointUpdate(ApiModel):
    path: str | None = Field(default=None, max_length=400)
    method: str | None = Field(default=None, max_length=10)
    streaming_supported: bool | None = None
    param_map: dict | None = None
    enabled: bool | None = None
    credential_id: uuid.UUID | None = None


class ModelTestStreamDone(ApiModel):
    """Terminal event of the streaming playground."""

    done: bool = True
    latency_ms: int = 0
    output_tokens: int = 0
    finish_reason: str | None = None
    error_code: str | None = None
    detail: str | None = None
