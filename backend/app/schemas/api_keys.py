"""Downstream API key contracts (frozen shape for milestone M4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import ApiModel, TimestampedRead


class ApiKeyCreate(ApiModel):
    name: str = Field(max_length=120)
    scopes: list[str] = Field(default_factory=list)
    rate_limit_per_min: int = Field(default=60, ge=1, le=100_000)
    quota_tokens: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None


class ApiKeyRead(TimestampedRead):
    id: uuid.UUID
    name: str
    prefix: str = Field(description="Display prefix, e.g. xrx_live_8f2a")
    masked: str = Field(description="Display form, e.g. xrx_live_8f2a…")
    scopes: list[str] = []
    rate_limit_per_min: int
    quota_tokens: int | None = None
    enabled: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class ApiKeyCreated(ApiKeyRead):
    """Returned exactly once, at creation time."""

    secret: str = Field(description="Full key. Never retrievable again.")
