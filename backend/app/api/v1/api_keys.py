"""Downstream API key administration (M4).

The secret is returned exactly once by ``POST /api-keys``. Every other route returns
the masked display form, so a leaked audit log or a screenshot cannot leak a key.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import PaginationDep, SessionDep
from app.auth.dependencies import client_ip, require_roles, user_agent
from app.models.enums import AdminRole
from app.models.identity import AdminUser
from app.schemas.api_keys import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    ApiKeyUpdate,
    ApiKeyUsage,
)
from app.schemas.common import MessageResponse, Page
from app.services.api_keys import ApiKeyService

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

#: A viewer may see the masked list (that is how the panel stays usable in a
#: read-only role); the secret is never returned after creation, and every write
#: stays with owner/admin.
READ_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR, AdminRole.VIEWER)
WRITE_ROLES = (AdminRole.OWNER, AdminRole.ADMIN)


@router.get("", response_model=Page[ApiKeyRead])
async def list_api_keys(
    session: SessionDep,
    pagination: PaginationDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
    enabled: Annotated[bool | None, Query(description="Filter by enabled flag.")] = None,
    include_revoked: Annotated[bool, Query(description="Include revoked keys.")] = True,
) -> Page[ApiKeyRead]:
    items, total = await ApiKeyService(session).list(
        search=pagination.search,
        enabled=enabled,
        include_revoked=include_revoked,
        offset=pagination.offset,
        limit=pagination.page_size,
    )
    return Page.build(items, total, pagination)


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ApiKeyCreated:
    return await ApiKeyService(session).create(
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )


@router.get("/{key_id}", response_model=ApiKeyRead)
async def get_api_key(
    key_id: uuid.UUID,
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> ApiKeyRead:
    service = ApiKeyService(session)
    return service.read(await service.get(key_id))


@router.patch("/{key_id}", response_model=ApiKeyRead)
async def update_api_key(
    key_id: uuid.UUID,
    payload: ApiKeyUpdate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ApiKeyRead:
    return await ApiKeyService(session).update(
        key_id,
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )


@router.post("/{key_id}/revoke", response_model=ApiKeyRead)
async def revoke_api_key(
    key_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ApiKeyRead:
    """«ابطال» — stops the key working while keeping its usage history."""
    return await ApiKeyService(session).revoke(
        key_id,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )


@router.delete("/{key_id}", response_model=MessageResponse)
async def delete_api_key(
    key_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> MessageResponse:
    await ApiKeyService(session).delete(
        key_id,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return MessageResponse(status="deleted")


@router.get("/{key_id}/usage", response_model=ApiKeyUsage)
async def api_key_usage(
    key_id: uuid.UUID,
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> ApiKeyUsage:
    """Token consumption and error count, aggregated from the attempt records."""
    return await ApiKeyService(session).usage(key_id)
