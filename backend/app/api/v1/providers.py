"""Provider and credential administration (M2).

Read routes are available to every authenticated role; configuration changes need
``admin`` or ``owner``; operational actions (a connectivity test, a credential
verification) are also allowed for ``operator``. Hiding a button in the Persian UI
is never the enforcement point — these dependencies are (PROMPT.md section 7).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import PaginationDep, SessionDep
from app.auth.dependencies import client_ip, require_roles, user_agent
from app.core.errors import NotFoundError
from app.models.enums import AdminRole, ProviderKind
from app.models.identity import AdminUser
from app.repositories.providers import CredentialRepository, ProviderRepository
from app.schemas.common import MessageResponse, Page
from app.schemas.providers import (
    CredentialCreate,
    CredentialRead,
    CredentialRotateRequest,
    CredentialUpdate,
    ProviderCreate,
    ProviderDeleteImpact,
    ProviderRead,
    ProviderTestResult,
    ProviderUpdate,
)
from app.services.provider_admin import CredentialService, ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])

READ_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR, AdminRole.VIEWER)
WRITE_ROLES = (AdminRole.OWNER, AdminRole.ADMIN)
ACTION_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR)

SortOrder = Annotated[
    str,
    Query(
        description="Sort key: priority (default), name, created_at or -name/-created_at.",
        max_length=32,
    ),
]


@router.get("", response_model=Page[ProviderRead])
async def list_providers(
    session: SessionDep,
    pagination: PaginationDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
    enabled: Annotated[bool | None, Query(description="Filter by enabled flag.")] = None,
    kind: Annotated[ProviderKind | None, Query(description="Filter by provider kind.")] = None,
    order_by: SortOrder = "priority",
) -> Page[ProviderRead]:
    service = ProviderService(session)
    items, total = await service.list(
        search=pagination.search,
        enabled=enabled,
        kind=kind,
        offset=pagination.offset,
        limit=pagination.page_size,
        order_by=order_by,
    )
    return Page.build(items, total, pagination)


@router.post("", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderCreate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ProviderRead:
    service = ProviderService(session)
    provider = await service.create(
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return await service.read(provider)


@router.get("/{provider_id}", response_model=ProviderRead)
async def get_provider(
    provider_id: uuid.UUID,
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> ProviderRead:
    service = ProviderService(session)
    return await service.read(await service.get(provider_id))


@router.patch("/{provider_id}", response_model=ProviderRead)
async def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderUpdate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ProviderRead:
    service = ProviderService(session)
    provider = await service.update(
        provider_id,
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return await service.read(provider)


@router.delete("/{provider_id}", response_model=MessageResponse)
async def delete_provider(
    provider_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> MessageResponse:
    service = ProviderService(session)
    await service.delete(
        provider_id,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return MessageResponse(status="deleted")


@router.post("/{provider_id}/test", response_model=ProviderTestResult)
async def test_provider(
    provider_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*ACTION_ROLES)),
    credential_id: Annotated[
        uuid.UUID | None,
        Query(
            description=(
                "Optional credential to probe; defaults to the provider's default credential."
            )
        ),
    ] = None,
) -> ProviderTestResult:
    service = ProviderService(session)
    return await service.test_connection(
        provider_id,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        credential_id=credential_id,
    )


@router.get("/{provider_id}/credentials", response_model=Page[CredentialRead])
async def list_credentials(
    provider_id: uuid.UUID,
    session: SessionDep,
    pagination: PaginationDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> Page[CredentialRead]:
    service = CredentialService(session)
    items, total = await service.list_for_provider(
        provider_id, offset=pagination.offset, limit=pagination.page_size
    )
    return Page.build(items, total, pagination)


@router.post(
    "/{provider_id}/credentials",
    response_model=CredentialRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    provider_id: uuid.UUID,
    payload: CredentialCreate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> CredentialRead:
    service = CredentialService(session)
    credential = await service.create(
        provider_id,
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return CredentialRead.model_validate(credential)


@router.patch("/{provider_id}/credentials/{credential_id}", response_model=CredentialRead)
async def update_credential(
    provider_id: uuid.UUID,
    credential_id: uuid.UUID,
    payload: CredentialUpdate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> CredentialRead:
    service = CredentialService(session)
    credential = await service.get(credential_id)
    if credential.provider_id != provider_id:
        raise NotFoundError(
            "The credential does not belong to this provider.", code="credential_not_found"
        )
    updated = await service.update(
        credential_id,
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return CredentialRead.model_validate(updated)


@router.post("/{provider_id}/credentials/{credential_id}/rotate", response_model=CredentialRead)
async def rotate_credential(
    provider_id: uuid.UUID,
    credential_id: uuid.UUID,
    payload: CredentialRotateRequest,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> CredentialRead:
    service = CredentialService(session)
    credential = await service.get(credential_id)
    if credential.provider_id != provider_id:
        raise NotFoundError(
            "The credential does not belong to this provider.", code="credential_not_found"
        )
    rotated = await service.rotate(
        credential_id,
        secret=payload.secret,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return CredentialRead.model_validate(rotated)


@router.post("/{provider_id}/credentials/{credential_id}/verify", response_model=ProviderTestResult)
async def verify_credential(
    provider_id: uuid.UUID,
    credential_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*ACTION_ROLES)),
) -> ProviderTestResult:
    service = CredentialService(session)
    credential = await service.get(credential_id)
    if credential.provider_id != provider_id:
        raise NotFoundError(
            "The credential does not belong to this provider.", code="credential_not_found"
        )
    return await service.verify(
        credential_id,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )


@router.delete("/{provider_id}/credentials/{credential_id}", response_model=MessageResponse)
async def delete_credential(
    provider_id: uuid.UUID,
    credential_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> MessageResponse:
    service = CredentialService(session)
    credential = await service.get(credential_id)
    if credential.provider_id != provider_id:
        raise NotFoundError(
            "The credential does not belong to this provider.", code="credential_not_found"
        )
    await service.delete(
        credential_id,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return MessageResponse(status="deleted")


@router.get("/{provider_id}/delete-impact", response_model=ProviderDeleteImpact)
async def provider_delete_impact(
    provider_id: uuid.UUID,
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> ProviderDeleteImpact:
    """Counts shown before deleting a provider, so the confirmation is honest."""
    return await ProviderService(session).delete_impact(provider_id)


@router.get("/{provider_id}/default-credential", response_model=CredentialRead | None)
async def default_credential(
    provider_id: uuid.UUID,
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> CredentialRead | None:
    """Credential an endpoint without an explicit binding would use."""
    repository = ProviderRepository(session)
    if await repository.get(provider_id) is None:
        raise NotFoundError("The provider does not exist.", code="provider_not_found")
    credential = await CredentialRepository(session).default_for_provider(provider_id)
    if credential is None:
        return None
    return CredentialRead.model_validate(credential)
