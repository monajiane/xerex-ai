"""Repositories for audit logs and platform settings."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.platform import Setting
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def list_recent(self, *, offset: int = 0, limit: int = 50) -> list[AuditLog]:
        statement = (
            select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())


class SettingRepository(BaseRepository[Setting]):
    model = Setting

    async def get_value(self, key: str, default: Any = None) -> Any:
        setting = await self.session.get(Setting, key)
        return default if setting is None else setting.value

    async def set_value(
        self,
        key: str,
        value: Any,
        *,
        updated_by=None,
        description=None,  # noqa: ANN001
    ) -> Setting:
        setting = await self.session.get(Setting, key)
        if setting is None:
            setting = Setting(key=key, value=value, description=description, updated_by=updated_by)
            self.session.add(setting)
        else:
            setting.value = value
            if description is not None:
                setting.description = description
            setting.updated_by = updated_by
        await self.session.flush()
        # ``updated_at`` is server generated; refresh it so callers can read it
        # without triggering a lazy load outside the async context.
        await self.session.refresh(setting)
        return setting

    async def all_settings(self) -> list[Setting]:
        result = await self.session.execute(select(Setting).order_by(Setting.key))
        return list(result.scalars().all())
