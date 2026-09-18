"""Smart routing engine skeleton.

M1 defines the strategy registry and the decision contract; candidate scoring and
the dry-run simulator land in M5. Nothing here fabricates routing decisions.

Persian UI note: the strategy names below are stable English enum values, shown
in the panel as «راهبرد» with Persian labels from the i18n layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import NotImplementedYetError
from app.models.enums import RoutingStrategy


@dataclass(frozen=True)
class StrategySpec:
    strategy: RoutingStrategy
    requires_priority: bool
    requires_weight: bool
    uses_health: bool
    uses_latency: bool
    uses_cost: bool
    implemented: bool
    summary: str


_STRATEGIES: tuple[StrategySpec, ...] = (
    StrategySpec(
        RoutingStrategy.PRIORITY,
        True,
        False,
        False,
        False,
        False,
        False,
        "Order candidates by provider priority, then by model order.",
    ),
    StrategySpec(
        RoutingStrategy.WEIGHTED,
        False,
        True,
        False,
        False,
        False,
        False,
        "Distribute traffic across candidates using configured weights.",
    ),
    StrategySpec(
        RoutingStrategy.ROUND_ROBIN,
        False,
        False,
        False,
        False,
        False,
        False,
        "Cycle through eligible candidates in order.",
    ),
    StrategySpec(
        RoutingStrategy.LATENCY_AWARE,
        False,
        True,
        True,
        True,
        False,
        False,
        "Prefer candidates with the lowest observed p95 latency.",
    ),
    StrategySpec(
        RoutingStrategy.COST_AWARE,
        False,
        False,
        False,
        False,
        True,
        False,
        "Prefer candidates with the lowest blended token cost.",
    ),
    StrategySpec(
        RoutingStrategy.FAILOVER,
        True,
        False,
        True,
        False,
        False,
        False,
        "Walk the fallback chain, skipping unhealthy candidates.",
    ),
)


def all_strategies() -> tuple[StrategySpec, ...]:
    return _STRATEGIES


def catalog() -> list[dict[str, object]]:
    return [
        {
            "strategy": spec.strategy.value,
            "requires_priority": spec.requires_priority,
            "requires_weight": spec.requires_weight,
            "uses_health": spec.uses_health,
            "uses_latency": spec.uses_latency,
            "uses_cost": spec.uses_cost,
            "implemented": spec.implemented,
            "summary": spec.summary,
            "milestone": "M5",
        }
        for spec in _STRATEGIES
    ]


class RoutingEngine:
    """Entry point for request routing.

    Raises ``NotImplementedYetError`` until M5 so no caller can silently receive
    a fabricated routing decision.
    """

    def __init__(self) -> None:
        self.strategies = {spec.strategy: spec for spec in _STRATEGIES}

    def resolve(self, *args: object, **kwargs: object) -> None:  # pragma: no cover - M5
        raise NotImplementedYetError(
            "The routing engine is delivered in milestone M5.",
            details={"milestone": "M5", "strategies": [s.strategy.value for s in _STRATEGIES]},
        )
