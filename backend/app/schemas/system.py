"""System information, capability flags and the delivery roadmap.

These contracts let the Persian admin panel render honest placeholder states:
a module is only shown as usable when its capability flag is ``implemented``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common import ApiModel

CapabilityState = Literal["implemented", "placeholder", "planned"]


class Capability(ApiModel):
    key: str
    state: CapabilityState
    milestone: str
    api_prefix: str | None = None


class PlannedEndpoint(ApiModel):
    method: str
    path: str
    summary: str
    milestone: str
    state: CapabilityState


class RoadmapModule(ApiModel):
    key: str
    milestone: str
    state: CapabilityState
    endpoints: list[PlannedEndpoint] = []


class LocalizationInfo(ApiModel):
    default_locale: str
    supported_locales: list[str]
    default_timezone: str


class SystemInfo(ApiModel):
    name: str
    version: str
    milestone: str
    environment: str
    api_version: str
    started_at: datetime
    uptime_seconds: float
    localization: LocalizationInfo
    capabilities: list[Capability]


class RoadmapResponse(ApiModel):
    current_milestone: str
    modules: list[RoadmapModule]
