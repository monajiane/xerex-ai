"""Routing rules and the dry-run simulator («مسیریابی») — M5.

The simulator runs the *same* engine and resolution the live gateway uses; it only
adds the explanation. That is the point of the screen: an operator can see why a
provider is chosen before changing a rule, and see it again afterwards.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import SessionDep
from app.auth.dependencies import client_ip, require_roles, user_agent
from app.core.errors import NotFoundError, ValidationError
from app.models.enums import AdminRole, RoutingStrategy
from app.models.identity import AdminUser
from app.router import engine as routing_engine
from app.schemas.common import MessageResponse
from app.schemas.routing import (
    RoutingRuleCreate,
    RoutingRuleRead,
    RoutingRuleUpdate,
    RoutingSimulationRequest,
    RoutingSimulationResult,
)
from app.services.routing import RoutingService

router = APIRouter(prefix="/routing", tags=["routing"])

READ_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR, AdminRole.VIEWER)
WRITE_ROLES = (AdminRole.OWNER, AdminRole.ADMIN)


@router.get("/strategies")
async def strategies(
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> dict[str, object]:
    """Strategy catalogue with the authority M5 actually implements."""
    return {"items": routing_engine.catalog(), "implemented": True, "milestone": "M5"}


@router.get("/rules", response_model=list[RoutingRuleRead])
async def list_rules(
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
    enabled: Annotated[bool | None, Query(description="Filter by enabled flag.")] = None,
) -> list[RoutingRuleRead]:
    return await RoutingService(session).list_rules(enabled=enabled)


@router.post("/rules", response_model=RoutingRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RoutingRuleCreate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> RoutingRuleRead:
    return await RoutingService(session).create_rule(
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )


@router.get("/rules/{rule_id}", response_model=RoutingRuleRead)
async def get_rule(
    rule_id: uuid.UUID,
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> RoutingRuleRead:
    rule = await RoutingService(session).get_rule(rule_id)
    return RoutingRuleRead.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=RoutingRuleRead)
async def update_rule(
    rule_id: uuid.UUID,
    payload: RoutingRuleUpdate,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> RoutingRuleRead:
    return await RoutingService(session).update_rule(
        rule_id,
        payload,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )


@router.delete("/rules/{rule_id}", response_model=MessageResponse)
async def delete_rule(
    rule_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*WRITE_ROLES)),
) -> MessageResponse:
    await RoutingService(session).delete_rule(
        rule_id,
        actor=current_user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return MessageResponse(status="deleted")


@router.post("/simulate", response_model=RoutingSimulationResult)
async def simulate(
    payload: RoutingSimulationRequest,
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> RoutingSimulationResult:
    """«شبیه‌سازی مسیریابی» — what would happen, with the reasoning, without a call."""
    service = RoutingService(session)
    model_name = payload.model
    if model_name is None and payload.rule_id is not None:
        rule = await service.get_rule(payload.rule_id)
        pattern = (rule.match_conditions or {}).get("model")
        model_name = pattern if isinstance(pattern, str) else None
    if not model_name:
        raise ValidationError(
            "A model name is required for a simulation.",
            code="routing_simulation_model_required",
        )
    return await service.simulate(
        model_name=model_name,
        strategy=payload.strategy,
        requested_tokens=payload.requested_tokens,
        actor=current_user,
        ip_address=client_ip(request),
    )


@router.get("/strategies/{strategy}")
async def strategy_detail(
    strategy: RoutingStrategy,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> dict[str, object]:
    spec = routing_engine.engine.strategies.get(strategy)
    if spec is None:
        raise NotFoundError("Unknown routing strategy.", code="routing_strategy_not_found")
    return {
        "strategy": spec.strategy.value,
        "requires_priority": spec.requires_priority,
        "requires_weight": spec.requires_weight,
        "uses_health": spec.uses_health,
        "uses_latency": spec.uses_latency,
        "uses_cost": spec.uses_cost,
        "implemented": True,
        "summary": spec.summary,
        "milestone": "M5",
    }
