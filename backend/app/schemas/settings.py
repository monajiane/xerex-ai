"""Platform settings contracts (key/value store)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import ApiModel

#: Settings the admin panel may change in the current milestone.
EDITABLE_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "ui.default_locale",
        "ui.numeral_style",
        "ui.theme",
        "ui.timezone",
        "ui.sidebar_collapsed",
        "notifications.email_enabled",
        "notifications.health_alerts",
        "retention.usage_days",
        "retention.logs_days",
    }
)


class SettingRead(ApiModel):
    key: str
    value: Any = None
    description: str | None = None
    updated_at: datetime | None = None
    editable: bool = False


class SettingUpdate(ApiModel):
    """Value payload for ``PUT /settings/{key}``.

    Value validation is key-aware and therefore lives in the settings service
    (the key is a path parameter, not a body field).
    """

    value: Any = Field(default=None, description="New JSON-compatible value.")


class SettingsBundle(ApiModel):
    items: list[SettingRead]
    supported_locales: list[str]
    default_locale: str
