"""Model registry, discovery and playground (M3).

Read routes are open to every authenticated role; the registry and discovery are
configuration (owner/admin); the playground is an operational action and also
allowed for operators. Streaming is served as Server-Sent Events so the Persian
panel can render tokens as they arrive without polling.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import PaginationDep, SessionDep
from app.auth.dependencies import client_ip, require_roles, user_agent
from app.models.enums import AdminRole
from app.models.identity import AdminUser
from app.schemas.common import MessageResponse, Page
from app.schemas.providers import (
    ModelCreate,
    ModelDiscoveryRequest,
    ModelDiscoveryResultDetail,
    ModelEndpointCreate,
    ModelEndpointRead,
    ModelEndpointUpdate,
    ModelRead,
    ModelTestRequest,
    ModelTestResult,
    ModelWrite,
)
from app.services.model_admin import (
    DiscoveryService,
    EndpointService,
    ModelService,
    PlaygroundService,
)

router = APIRouter(prefix="/models", tags=["models"])

READ_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR, AdminRole.VIEWER)
WRITE_ROLES = (AdminRole.OWNER, AdminRole.ADMIN)
ACTION_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR)

SortOrder = Annotated[
    str,
    Query(
        description="Sort key: name (default), -name, created_at, -created_at or provider.",
        max_length=32,
    ),
]


@router.get("", response_model=Page[ModelRead])
async def list_models(
    session: SessionDep,
    pagination: PaginationDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
    provider_id: Annotated[uuid.UUID | None, Query(description="Filter by provider.")] = None,
    enabled: Annotated[bool | None, Query(description="Filter by enabled flag.")] = None,
    deprecated: Annotated[bool | None, Query(description="Filter by deprecation flag.")] = None,
    order_by: SortOrder = "name",
) -> Page[ModelRead]:
    items, total = await ModelService(session).list(
        search=pagination.search,
        provider_id=provider_id,
        enabled=enabled,
        deprecated=deprecated,
        offset=pagination.offset,
        limit=pagination.page_size,
        order_by=order_by,
    )
    return Page.build(items, total, pagination)


@router.post("", response_model=ModelRead, status_code=status.HTTP_201_CREATED)
async def create_model(
    payload: ModelCreate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ModelRead:
    service = ModelService(session)
    model = await service.create(
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return await service.read(model)


@router.post("/discover", response_model=ModelDiscoveryResultDetail)
async def discover_models(
    payload: ModelDiscoveryRequest,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ModelDiscoveryResultDetail:
    """«کشف مدل‌ها» — ask the provider what it serves and reconcile the registry."""
    return await DiscoveryService(session).discover(
        payload.provider_id,
        overwrite_existing=payload.overwrite_existing,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )


@router.get("/{model_id}", response_model=ModelRead)
async def get_model(
    model_id: uuid.UUID,
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> ModelRead:
    service = ModelService(session)
    return await service.read(await service.get(model_id))


@router.patch("/{model_id}", response_model=ModelRead)
async def update_model(
    model_id: uuid.UUID,
    payload: ModelWrite,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ModelRead:
    service = ModelService(session)
    model = await service.update(
        model_id,
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return await service.read(model)


@router.delete("/{model_id}", response_model=MessageResponse)
async def delete_model(
    model_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> MessageResponse:
    await ModelService(session).delete(
        model_id,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return MessageResponse(status="deleted")


@router.post("/{model_id}/test", response_model=ModelTestResult)
async def test_model(
    model_id: uuid.UUID,
    payload: ModelTestRequest,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*ACTION_ROLES)),
) -> ModelTestResult:
    """«آزمایش مدل» — one prompt through the real adapter, with real token counts."""
    return await PlaygroundService(session).run(
        model_id,
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )


@router.post("/{model_id}/test/stream")
async def stream_model_test(
    model_id: uuid.UUID,
    payload: ModelTestRequest,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*ACTION_ROLES)),
) -> StreamingResponse:
    """Server-Sent Events variant of the playground used by «پاسخ جریانی»."""
    service = PlaygroundService(session)

    async def event_stream() -> AsyncIterator[str]:
        async for event in service.stream(model_id, payload, actor=current_user):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------------------------------- #
# Model endpoints — «نقاط اتصال مدل»
# --------------------------------------------------------------------------- #
@router.get("/{model_id}/endpoints", response_model=list[ModelEndpointRead])
async def list_endpoints(
    model_id: uuid.UUID,
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> list[ModelEndpointRead]:
    return list(await EndpointService(session).list_for_model(model_id))


@router.post(
    "/{model_id}/endpoints", response_model=ModelEndpointRead, status_code=status.HTTP_201_CREATED
)
async def create_endpoint(
    model_id: uuid.UUID,
    payload: ModelEndpointCreate,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ModelEndpointRead:
    endpoint = await EndpointService(session).create(model_id, payload, actor=current_user)
    return ModelEndpointRead.model_validate(endpoint)


@router.patch("/{model_id}/endpoints/{endpoint_id}", response_model=ModelEndpointRead)
async def update_endpoint(
    model_id: uuid.UUID,
    endpoint_id: uuid.UUID,
    payload: ModelEndpointUpdate,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> ModelEndpointRead:
    endpoint = await EndpointService(session).update(
        model_id, endpoint_id, payload, actor=current_user
    )
    return ModelEndpointRead.model_validate(endpoint)


@router.delete("/{model_id}/endpoints/{endpoint_id}", response_model=MessageResponse)
async def delete_endpoint(
    model_id: uuid.UUID,
    endpoint_id: uuid.UUID,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> MessageResponse:
    await EndpointService(session).delete(model_id, endpoint_id, actor=current_user)
    return MessageResponse(status="deleted")
