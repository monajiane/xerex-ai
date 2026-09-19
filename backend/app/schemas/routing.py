"""Routing contracts (M5): rules, simulation requests and explained decisions."""

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


class RoutingRuleUpdate(ApiModel):
    """Partial update; omitted fields keep their stored value."""

    name: str | None = Field(default=None, max_length=120)
    strategy: RoutingStrategy | None = None
    match_conditions: dict | None = None
    target_model_ids: list[uuid.UUID] | None = None
    fallback_chain: list[uuid.UUID] | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)


class RoutingRuleRead(RoutingRuleBase, TimestampedRead):
    id: uuid.UUID


class RoutingSimulationRequest(ApiModel):
    """A dry run: which model, which strategy, how many tokens.

    ``strategy`` overrides the matching rule for this simulation only — it never
    changes stored configuration, so an operator can compare strategies safely.
    """

    rule_id: uuid.UUID | None = None
    model: str | None = Field(default=None, max_length=160)
    strategy: RoutingStrategy | None = None
    requested_tokens: int = Field(default=1000, ge=0, le=10_000_000)
    api_key_id: uuid.UUID | None = None


class RoutingCandidate(ApiModel):
    """One candidate in a simulated decision, with the reasons it sits where it sits."""

    model_id: uuid.UUID | None = None
    model_name: str | None = None
    provider_id: uuid.UUID | None = None
    provider_name: str | None = None
    credential_id: uuid.UUID | None = None
    endpoint_id: uuid.UUID | None = None
    score: float = 0.0
    eligible: bool = True
    latency_ms: int | None = None
    price_per_1m: float | None = None
    estimated_cost: float | None = None
    #: Stable English tokens (``provider_priority=1``, ``excluded_health_down``); the
    #: Persian panel renders them through the i18n layer.
    reasons: list[str] = []


class RoutingSimulationResult(ApiModel):
    model: str
    strategy: RoutingStrategy
    rule_id: uuid.UUID | None = None
    rule_name: str | None = None
    candidates: list[RoutingCandidate] = []
    selected_model_id: uuid.UUID | None = None
    selected_provider_id: uuid.UUID | None = None
    explanation: list[str] = []
