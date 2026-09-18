"""Process level runtime state (uptime, boot time)."""

from __future__ import annotations

import time

from app.core.config import settings

_PROCESS_STARTED_AT = time.time()


def started_at() -> float:
    """Unix timestamp of process start."""
    return _PROCESS_STARTED_AT


def uptime_seconds() -> float:
    return round(time.time() - _PROCESS_STARTED_AT, 3)


def app_identity() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "milestone": settings.milestone,
        "environment": settings.environment,
    }
