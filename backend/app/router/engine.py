"""Smart routing engine (M5).

The engine is **pure**: given candidates (each carrying the provider priority and
weight, the observed health and latency, and the model price), it returns an ordered
decision with an explanation per candidate. Everything that touches the database lives
in :mod:`app.services.routing`, so the ordering rules can be unit tested without a
session, and the dry-run simulator shares exactly the same code as live traffic —
"what would happen" and "what happens" cannot drift apart.

Persian UI note: ``reasons`` are stable English tokens (``provider_priority=1``); the
panel renders them through the i18n layer, so no Persian string is ever produced here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import HealthStatus, RoutingStrategy

#: How healthy a candidate has to be to stay in the primary list. ``down`` is the only
#: status that removes a candidate — everything else is a preference, not a veto,
#: because one stale observation must not take a provider out of service.
ELIGIBLE_STATUSES = (
    HealthStatus.HEALTHY,
    HealthStatus.DEGRADED,
    HealthStatus.RATE_LIMITED,
    HealthStatus.UNKNOWN,
)

#: Preference order used by the health-aware strategies.
_HEALTH_RANK = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.DEGRADED: 1,
    HealthStatus.UNKNOWN: 2,
    HealthStatus.RATE_LIMITED: 3,
    HealthStatus.DOWN: 9,
}


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
        True,
        "Order candidates by provider priority, then by weight.",
    ),
    StrategySpec(
        RoutingStrategy.WEIGHTED,
        False,
        True,
        True,
        False,
        False,
        True,
        "Score candidates by weight, preferring healthy ones.",
    ),
    StrategySpec(
        RoutingStrategy.ROUND_ROBIN,
        False,
        False,
        False,
        False,
        False,
        True,
        "Cycle through eligible candidates, one request at a time.",
    ),
    StrategySpec(
        RoutingStrategy.LATENCY_AWARE,
        False,
        False,
        True,
        True,
        False,
        True,
        "Prefer candidates with the lowest observed latency.",
    ),
    StrategySpec(
        RoutingStrategy.COST_AWARE,
        False,
        False,
        False,
        False,
        True,
        True,
        "Prefer candidates with the lowest blended token cost.",
    ),
    StrategySpec(
        RoutingStrategy.FAILOVER,
        True,
        False,
        True,
        True,
        True,
        True,
        "Walk the fallback chain, skipping candidates whose health is down.",
    ),
)


#: Every strategy shipped in M5 is implemented; the catalog is honest about it.
_IMPLEMENTED = True


@dataclass
class CandidateScore:
    """One candidate plus why it got its position."""

    key: str
    score: float
    rank: int = 0
    eligible: bool = True
    reasons: list[str] = field(default_factory=list)
    health: HealthStatus | None = None
    latency_ms: int | None = None
    price_per_1m: float | None = None
    payload: object | None = None


@dataclass
class Decision:
    strategy: RoutingStrategy
    candidates: list[CandidateScore]
    explanation: list[str] = field(default_factory=list)

    @property
    def ordered(self) -> list[CandidateScore]:
        """Eligible candidates first, in rank order; the rest as a trailing fallback."""
        eligible = [item for item in self.candidates if item.eligible]
        ineligible = [item for item in self.candidates if not item.eligible]
        return sorted(eligible, key=lambda item: item.rank) + sorted(
            ineligible, key=lambda item: item.rank
        )

    @property
    def selected(self) -> CandidateScore | None:
        ordered = self.ordered
        return ordered[0] if ordered else None


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
            "implemented": _IMPLEMENTED,
            "summary": spec.summary,
            "milestone": "M5",
        }
        for spec in _STRATEGIES
    ]


def _blended_price(input_price: float | None, output_price: float | None) -> float | None:
    """Cost of 1M input + 1M output tokens — the honest number when only prices are known."""
    if input_price is None and output_price is None:
        return None
    return float(input_price or 0) + float(output_price or 0)


class RoutingEngine:
    """Deterministic, explainable ordering of routing candidates.

    Every strategy ends with the same tie-breakers (priority, then weight, then the
    candidate key) so the order is stable: an operator can reproduce a decision and a
    test can assert it.
    """

    def __init__(self) -> None:
        self.strategies = {spec.strategy: spec for spec in _STRATEGIES}

    # -- public API ----------------------------------------------------------
    def rank(
        self,
        candidates: list[CandidateScore],
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
        *,
        offset: int = 0,
    ) -> Decision:
        for candidate in candidates:
            if candidate.health is not None and candidate.health not in ELIGIBLE_STATUSES:
                candidate.eligible = False

        rotated: list[CandidateScore] | None = None
        if strategy == RoutingStrategy.ROUND_ROBIN:
            # Rotation happens on the *preferred* candidates only; the ones kept as a
            # last resort stay at the end, in their original order.
            eligible = [candidate for candidate in candidates if candidate.eligible]
            rest = [candidate for candidate in candidates if not candidate.eligible]
            if eligible:
                position = offset % len(eligible)
                eligible = eligible[position:] + eligible[:position]
                for index, candidate in enumerate(eligible):
                    candidate.reasons.append(f"round_robin_offset={offset}")
                    if index == 0:
                        candidate.reasons.append("round_robin_turn")
            rotated = eligible + rest

        ordered = self._sort(rotated if rotated is not None else candidates, strategy)
        for index, candidate in enumerate(ordered):
            if candidate.eligible:
                candidate.rank = index

        explanation = [
            f"strategy={strategy.value}",
            f"candidates={len(candidates)}",
            f"eligible={sum(1 for candidate in ordered if candidate.eligible)}",
        ]
        if offset:
            explanation.append(f"round_robin_offset={offset}")
        return Decision(strategy=strategy, candidates=ordered, explanation=explanation)

    def _sort(
        self, candidates: list[CandidateScore], strategy: RoutingStrategy
    ) -> list[CandidateScore]:
        """Sort by the strategy's primary criterion.

        The candidate key is the final element of every key tuple, so equal primary
        scores still produce a stable, reproducible order.
        """
        if strategy == RoutingStrategy.COST_AWARE:
            ordered = sorted(candidates, key=self._cost_key)
            for candidate in ordered:
                self._explain(candidate, price=True)
            return ordered
        if strategy == RoutingStrategy.LATENCY_AWARE:
            ordered = sorted(candidates, key=self._latency_key)
            for candidate in ordered:
                self._explain(candidate, latency=True)
            return ordered
        if strategy == RoutingStrategy.WEIGHTED:
            ordered = sorted(candidates, key=self._weight_key)
            for candidate in ordered:
                candidate.reasons.append(f"weight={self._weight_of(candidate):g}")
                self._explain(candidate, health=True)
            return ordered
        if strategy == RoutingStrategy.FAILOVER:
            ordered = sorted(candidates, key=self._health_key)
            for candidate in ordered:
                self._explain(candidate, health=True, latency=True, price=True)
            return ordered
        if strategy == RoutingStrategy.ROUND_ROBIN:
            return candidates
        # priority (the default) and any unknown value fall back to the explicit order
        ordered = sorted(candidates, key=self._priority_key)
        for candidate in ordered:
            candidate.reasons.append(f"provider_priority={self._priority_of(candidate):g}")
        return ordered

    @staticmethod
    def _explain(
        candidate: CandidateScore,
        *,
        health: bool = False,
        latency: bool = False,
        price: bool = False,
    ) -> None:
        """Attach the observations a human (or the simulator) needs to follow along."""
        if health:
            candidate.reasons.append(f"health={(candidate.health or HealthStatus.UNKNOWN).value}")
        if latency:
            if candidate.latency_ms is None:
                candidate.reasons.append("no_latency_sample")
            else:
                candidate.reasons.append(f"observed_latency_ms={candidate.latency_ms}")
        if price:
            if candidate.price_per_1m is None:
                candidate.reasons.append("no_price_data")
            else:
                candidate.reasons.append(f"blended_price={candidate.price_per_1m:g}")
        if not candidate.eligible:
            candidate.reasons.append("excluded_health_down")

    # -- keys ---------------------------------------------------------------
    @staticmethod
    def _payload(candidate: CandidateScore) -> dict:
        payload = candidate.payload
        return payload if isinstance(payload, dict) else {}

    def _priority_of(self, candidate: CandidateScore) -> float:
        return float(self._payload(candidate).get("priority", 100))

    def _weight_of(self, candidate: CandidateScore) -> float:
        return float(self._payload(candidate).get("weight", 100))

    def _health_of(self, candidate: CandidateScore) -> int:
        health = candidate.health or HealthStatus.UNKNOWN
        return _HEALTH_RANK.get(health, 5)

    def _priority_key(self, candidate: CandidateScore) -> tuple[int, float, str]:
        if not candidate.eligible:
            return (2, self._priority_of(candidate), candidate.key)
        return (0, self._priority_of(candidate), candidate.key)

    def _weight_key(self, candidate: CandidateScore) -> tuple[int, float, float, str]:
        # Higher weight first, healthy providers before degraded ones.
        if not candidate.eligible:
            return (2, 0.0, self._priority_of(candidate), candidate.key)
        return (0, -self._weight_of(candidate), self._priority_of(candidate), candidate.key)

    def _latency_key(self, candidate: CandidateScore) -> tuple[int, float, float, str]:
        # Candidates without a sample are placed after the measured ones but before
        # anything that is out of service: "unknown" is not "fast".
        if not candidate.eligible:
            return (2, float("inf"), 0.0, candidate.key)
        latency = candidate.latency_ms
        if latency is None:
            return (1, float("inf"), self._priority_of(candidate), candidate.key)
        return (0, float(latency), self._priority_of(candidate), candidate.key)

    def _cost_key(self, candidate: CandidateScore) -> tuple[int, float, float, str]:
        if not candidate.eligible:
            return (2, float("inf"), 0.0, candidate.key)
        price = candidate.price_per_1m
        if price is None:
            return (1, float("inf"), self._priority_of(candidate), candidate.key)
        return (0, price, self._priority_of(candidate), candidate.key)

    def _health_key(self, candidate: CandidateScore) -> tuple[int, float, float, str]:
        return (
            self._health_of(candidate),
            self._priority_of(candidate),
            self._priority_of(candidate),
            candidate.key,
        )


#: One process-wide engine; it holds no state, so sharing it is safe.
engine = RoutingEngine()
