"""Routing engine contracts (frozen shape for milestone M5)."""

from __future__ import annotations

import uuid

from pydantic import Field

from app.models.enums import RoutingStrategy
from app.schemas.common import ApiModel, TimestampedRead


class RoutingRuleBase(ApiModel):
    name: str = Field(max_length=120)
    strategy: RoutingStrategy = RoutingStrategy.PRIORITY
    match_conditions: dict | None = None
    target_model_ids: list[uuid.UUID] = []
    fallback_chain: list[uuid.UUID] = []
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10_000)


class RoutingRuleCreate(RoutingRuleBase):
    pass


class RoutingRuleRead(RoutingRuleBase, TimestampedRead):
    id: uuid.UUID


class RoutingSimulationRequest(ApiModel):
    rule_id: uuid.UUID | None = None
    model: str | None = None
    requested_tokens: int = Field(default=1000, ge=0)
    api_key_id: uuid.UUID | None = None


class RoutingCandidate(ApiModel):
    model_id: uuid.UUID | None = None
    provider_name: str | None = None
    score: float
    eligible: bool
    reason: str | None = None


class RoutingSimulationResult(ApiModel):
    strategy: RoutingStrategy
    candidates: list[RoutingCandidate] = []
    selected_model_id: uuid.UUID | None = None
    fallback_chain: list[uuid.UUID] = []
    explanation: str
