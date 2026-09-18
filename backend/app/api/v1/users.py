"""Administrator management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import PaginationDep, SessionDep
from app.auth.dependencies import client_ip, require_roles, user_agent
from app.auth.service import AuthService
from app.core.errors import NotFoundError
from app.models.enums import AdminRole
from app.models.identity import AdminUser
from app.repositories.identity import AdminUserRepository
from app.schemas.auth import AdminUserCreate, AdminUserRead, AdminUserUpdate
from app.schemas.common import Page

router = APIRouter(prefix="/admin-users", tags=["admin-users"])

READ_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR, AdminRole.VIEWER)
WRITE_ROLES = (AdminRole.OWNER, AdminRole.ADMIN)


@router.get("", response_model=Page[AdminUserRead])
async def list_users(
    session: SessionDep,
    pagination: PaginationDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> Page[AdminUserRead]:
    repository = AdminUserRepository(session)
    users = await repository.list(
        offset=pagination.offset,
        limit=pagination.page_size,
        order_by=AdminUser.created_at.asc(),
    )
    total = await repository.count()
    return Page.build([AdminUserRead.model_validate(user) for user in users], total, pagination)


@router.post("", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> AdminUserRead:
    service = AuthService(session)
    user = await service.create_user(
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return AdminUserRead.model_validate(user)


@router.patch("/{user_id}", response_model=AdminUserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> AdminUserRead:
    repository = AdminUserRepository(session)
    user = await repository.get(user_id)
    if user is None:
        raise NotFoundError("The administrator account does not exist.")
    changes = payload.model_dump(exclude_unset=True)
    updated = await AuthService(session).update_user(user, changes=changes, actor=current_user)
    return AdminUserRead.model_validate(updated)
