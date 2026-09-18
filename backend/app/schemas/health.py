"""System health contracts.

Field values (``healthy`` / ``degraded`` / ``down``) are English enum values;
the Persian admin panel renders them as «سالم» / «کاهش‌یافته» / «قطع».
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel

ComponentStatus = Literal["healthy", "degraded", "down", "unknown"]
OverallStatus = Literal["healthy", "degraded", "down"]


class ComponentHealth(ApiModel):
    name: str
    status: ComponentStatus
    latency_ms: float | None = None
    version: str | None = None
    dialect: str | None = None
    required: bool | None = None
    degraded_ok: bool | None = None
    error: str | None = None
    detail: str | None = None


class LivenessResponse(ApiModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str


class ReadinessResponse(ApiModel):
    status: OverallStatus
    service: str
    version: str
    milestone: str
    environment: str
    checked_at: datetime
    uptime_seconds: float
    components: list[ComponentHealth] = Field(default_factory=list)
