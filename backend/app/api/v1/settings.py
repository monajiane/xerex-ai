"""Platform settings (localization, presentation, retention)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep
from app.auth.dependencies import require_roles
from app.models.enums import AdminRole
from app.models.identity import AdminUser
from app.schemas.settings import SettingRead, SettingsBundle, SettingUpdate
from app.services.settings import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])

READ_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR, AdminRole.VIEWER)
WRITE_ROLES = (AdminRole.OWNER, AdminRole.ADMIN)


@router.get("", response_model=SettingsBundle)
async def read_settings(
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> SettingsBundle:
    return await SettingsService(session).bundle()


@router.put("/{key}", response_model=SettingRead)
async def update_setting(
    key: str,
    payload: SettingUpdate,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> SettingRead:
    return await SettingsService(session).update(key, payload.value, actor=current_user)
