"""Platform settings service with typed defaults."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.core.errors import ValidationError
from app.models.enums import AuditAction
from app.models.identity import AdminUser
from app.repositories.platform import SettingRepository
from app.schemas.settings import EDITABLE_SETTING_KEYS, SettingRead, SettingsBundle
from app.services.audit import AuditService

#: Default value for every known setting key.
DEFAULT_SETTINGS: dict[str, Any] = {
    "ui.default_locale": app_settings.default_locale,
    "ui.numeral_style": "persian",
    "ui.theme": "system",
    "ui.timezone": app_settings.default_timezone,
    "ui.sidebar_collapsed": False,
    "notifications.email_enabled": False,
    "notifications.health_alerts": True,
    "retention.usage_days": 90,
    "retention.logs_days": 30,
}


NUMERAL_STYLES = ("persian", "latin")
THEMES = ("light", "dark", "system")
RETENTION_KEYS = ("retention.usage_days", "retention.logs_days")
BOOLEAN_KEYS = (
    "ui.sidebar_collapsed",
    "notifications.email_enabled",
    "notifications.health_alerts",
)


def validate_setting_value(key: str, value: Any) -> None:
    """Key-aware validation; raises ``ValidationError`` with a stable code."""

    def reject(reason: str, allowed: Any = None) -> None:
        raise ValidationError(
            "The setting value is invalid.",
            code="invalid_setting_value",
            details={"key": key, "reason": reason, "allowed": allowed},
        )

    if key == "ui.default_locale" and value not in app_settings.supported_locales:
        reject("unsupported_locale", app_settings.supported_locales)
    elif key == "ui.numeral_style" and value not in NUMERAL_STYLES:
        reject("unsupported_numeral_style", list(NUMERAL_STYLES))
    elif key == "ui.theme" and value not in THEMES:
        reject("unsupported_theme", list(THEMES))
    elif key == "ui.timezone":
        try:
            ZoneInfo(str(value))
        except (ZoneInfoNotFoundError, ValueError):
            reject("unknown_timezone")
    elif key in RETENTION_KEYS and (
        not isinstance(value, int) or isinstance(value, bool) or value < 1
    ):
        reject("expected_positive_integer")
    elif key in BOOLEAN_KEYS and not isinstance(value, bool):
        reject("expected_boolean")


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = SettingRepository(session)
        self.audit = AuditService(session)

    async def bundle(self) -> SettingsBundle:
        stored = {setting.key: setting for setting in await self.repository.all_settings()}
        items: list[SettingRead] = []
        for key, default in DEFAULT_SETTINGS.items():
            setting = stored.get(key)
            items.append(
                SettingRead(
                    key=key,
                    value=default if setting is None else setting.value,
                    description=setting.description if setting else None,
                    updated_at=setting.updated_at if setting else None,
                    editable=key in EDITABLE_SETTING_KEYS,
                )
            )
        return SettingsBundle(
            items=items,
            supported_locales=app_settings.supported_locales,
            default_locale=app_settings.default_locale,
        )

    async def update(self, key: str, value: Any, *, actor: AdminUser) -> SettingRead:
        if key not in DEFAULT_SETTINGS:
            raise ValidationError(
                "Unknown setting key.", code="unknown_setting", details={"key": key}
            )
        if key not in EDITABLE_SETTING_KEYS:
            raise ValidationError(
                "This setting is managed by the deployment environment.",
                code="setting_read_only",
                details={"key": key},
            )
        validate_setting_value(key, value)
        setting = await self.repository.set_value(key, value, updated_by=actor.id)
        await self.audit.record(
            AuditAction.SETTINGS_UPDATED,
            actor=actor,
            entity_type="setting",
            entity_id=key,
            diff={"key": key, "value": value},
        )
        return SettingRead(
            key=key,
            value=setting.value,
            description=setting.description,
            updated_at=setting.updated_at,
            editable=True,
        )
