"""Administrative audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep
from app.auth.dependencies import require_roles
from app.models.enums import AdminRole
from app.models.identity import AdminUser
from app.repositories.platform import AuditLogRepository
from app.schemas.audit import AuditLogRead
from app.schemas.common import Page

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=Page[AuditLogRead])
async def list_audit_logs(
    session: SessionDep,
    page: int = 1,
    page_size: int = 50,
    _: AdminUser = Depends(require_roles(AdminRole.OWNER, AdminRole.ADMIN)),
) -> Page[AuditLogRead]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    repository = AuditLogRepository(session)
    entries = await repository.list_recent(offset=(page - 1) * page_size, limit=page_size)
    total = await repository.count()
    return Page(
        items=[AuditLogRead.model_validate(entry) for entry in entries],
        total=total,
        page=page,
        page_size=page_size,
    )
