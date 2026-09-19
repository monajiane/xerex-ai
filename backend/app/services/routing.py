"""Routing: candidate resolution, rules and the dry-run simulator (M5).

Two responsibilities live here on purpose:

* **Resolution** — "which provider, credential and endpoint can serve this model?".
  It is the single implementation of that question: the live gateway and the simulator
  both call it, so a simulated decision cannot disagree with reality.
* **Rules** — named configurations (strategy + match conditions + fallback chain) that
  an operator manages in «مسیریابی», with the explanation of every decision.

The ordering rules themselves are pure and live in :mod:`app.router.engine`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from fnmatch import fnmatch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.enums import AuditAction, HealthStatus, RoutingStrategy
from app.models.health import HealthCheck
from app.models.identity import AdminUser
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.models.routing import RoutingRule
from app.models.usage import UsageRecord
from app.router import engine as routing_engine
from app.schemas.routing import (
    RoutingCandidate,
    RoutingRuleCreate,
    RoutingRuleRead,
    RoutingRuleUpdate,
    RoutingSimulationResult,
)
from app.services.audit import AuditService

logger = get_logger(__name__)

#: Recent attempts considered when the health history has no latency sample yet.
LATENCY_SAMPLE_SIZE = 20

#: How many successful attempts are needed before an average latency is trusted.
MIN_LATENCY_SAMPLES = 1


@dataclass
class Candidate:
    """One possible upstream attempt for a requested model."""

    provider: Provider
    model: Model
    credential: ProviderCredential
    endpoint: ModelEndpoint | None

    @property
    def key(self) -> str:
        """Stable identity used by the engine and by the simulator output."""
        return f"{self.provider.slug}:{self.model.name}"

    @property
    def streaming_supported(self) -> bool:
        if self.endpoint is None:
            return True
        return self.endpoint.streaming_supported


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
async def first_endpoint(session: AsyncSession, model: Model) -> ModelEndpoint | None:
    statement = (
        select(ModelEndpoint)
        .where(ModelEndpoint.model_id == model.id, ModelEndpoint.enabled.is_(True))
        .order_by(ModelEndpoint.created_at.asc())
    )
    return (await session.execute(statement)).scalars().first()


async def credential_for(
    session: AsyncSession,
    model: Model,
    provider: Provider,
    endpoint: ModelEndpoint | None,
) -> ProviderCredential | None:
    """Endpoint-bound credential first, otherwise the provider's oldest credential."""
    if endpoint is not None and endpoint.credential_id is not None:
        credential = await session.get(ProviderCredential, endpoint.credential_id)
        if credential is not None:
            return credential
    statement = (
        select(ProviderCredential)
        .where(ProviderCredential.provider_id == provider.id)
        .order_by(ProviderCredential.created_at.asc())
    )
    return (await session.execute(statement)).scalars().first()


async def resolve_candidates(session: AsyncSession, model_name: str) -> list[Candidate]:
    """Every enabled way to reach ``model_name``; candidates without a usable
    credential are dropped because they cannot serve a request."""
    statement = (
        select(Model, Provider)
        .join(Provider, Provider.id == Model.provider_id)
        .where(
            Model.name == model_name,
            Model.enabled.is_(True),
            Provider.enabled.is_(True),
        )
        .order_by(Provider.priority.asc(), Provider.weight.desc(), Model.created_at.asc())
    )
    rows = (await session.execute(statement)).all()
    candidates: list[Candidate] = []
    for model, provider in rows:
        endpoint = await first_endpoint(session, model)
        credential = await credential_for(session, model, provider, endpoint)
        if credential is None or credential.status.value == "revoked":
            continue
        candidates.append(
            Candidate(provider=provider, model=model, credential=credential, endpoint=endpoint)
        )
    return candidates


# --------------------------------------------------------------------------- #
# Observations used for scoring
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProviderSignal:
    status: HealthStatus
    latency_ms: int | None
    source: str  # "health" | "usage" | "none"


async def provider_signals(session: AsyncSession, provider_ids: list[uuid.UUID]) -> dict:
    """Latest health status and a latency estimate per provider.

    Latency comes from the health history when it exists and from the most recent
    successful attempts otherwise, so a freshly added provider is not treated as
    instantly fast (``unknown`` is ranked after measured candidates).
    """
    signals: dict[uuid.UUID, ProviderSignal] = {}
    if not provider_ids:
        return signals

    for provider_id in provider_ids:
        check = (
            (
                await session.execute(
                    select(HealthCheck)
                    .where(HealthCheck.provider_id == provider_id)
                    .order_by(HealthCheck.checked_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

        status = HealthStatus(check.status) if check is not None else HealthStatus.UNKNOWN
        latency = check.latency_ms if check is not None and check.latency_ms else None
        source = "health" if latency is not None else "none"

        if latency is None:
            average = (
                await session.execute(
                    select(func.avg(UsageRecord.latency_ms), func.count(UsageRecord.id)).where(
                        UsageRecord.provider_id == provider_id,
                        UsageRecord.error_code.is_(None),
                        UsageRecord.latency_ms > 0,
                    )
                )
            ).one()
            average_latency, samples = average
            if average_latency is not None and int(samples or 0) >= MIN_LATENCY_SAMPLES:
                latency = int(average_latency)
                source = "usage"

        signals[provider_id] = ProviderSignal(status=status, latency_ms=latency, source=source)

    return signals


def blended_price(model: Model) -> float | None:
    """USD per 1M input tokens plus 1M output tokens; ``None`` when prices are unknown."""
    if model.input_price_per_1m is None and model.output_price_per_1m is None:
        return None
    return float(model.input_price_per_1m or 0) + float(model.output_price_per_1m or 0)


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #
def rule_matches(rule: RoutingRule, *, model_name: str, model_id: uuid.UUID) -> bool:
    """A rule matches by explicit model id, by name pattern, or (empty) for everything."""
    targets = [str(item) for item in (rule.target_model_ids or [])]
    if str(model_id) in targets:
        return True
    conditions = rule.match_conditions or {}
    pattern = conditions.get("model") if isinstance(conditions, dict) else None
    if isinstance(pattern, str) and pattern:
        return fnmatch(model_name, pattern) or pattern == model_name
    return not targets and not pattern


class RoutingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    # -- rules ---------------------------------------------------------------
    async def list_rules(self, *, enabled: bool | None = None) -> list[RoutingRuleRead]:
        statement = select(RoutingRule).order_by(
            RoutingRule.priority.asc(), RoutingRule.created_at.asc()
        )
        if enabled is not None:
            statement = statement.where(RoutingRule.enabled.is_(enabled))
        rows = (await self.session.execute(statement)).scalars().all()
        return [RoutingRuleRead.model_validate(row) for row in rows]

    async def get_rule(self, rule_id: uuid.UUID) -> RoutingRule:
        rule = await self.session.get(RoutingRule, rule_id)
        if rule is None:
            raise NotFoundError("The routing rule does not exist.", code="routing_rule_not_found")
        return rule

    async def create_rule(
        self,
        payload: RoutingRuleCreate,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RoutingRuleRead:
        await self._assert_name_free(payload.name)
        self._validate_conditions(payload.match_conditions)
        rule = RoutingRule(
            name=payload.name,
            strategy=payload.strategy,
            match_conditions=payload.match_conditions,
            target_model_ids=[str(item) for item in payload.target_model_ids],
            fallback_chain=[str(item) for item in payload.fallback_chain],
            enabled=payload.enabled,
            priority=payload.priority,
            created_by=actor.id if actor else None,
        )
        self.session.add(rule)
        await self.session.flush()
        await self.audit.record(
            AuditAction.ROUTING_RULE_CREATED,
            actor=actor,
            entity_type="routing_rule",
            entity_id=str(rule.id),
            diff={
                "name": rule.name,
                "strategy": rule.strategy.value,
                "priority": rule.priority,
                "enabled": rule.enabled,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return RoutingRuleRead.model_validate(rule)

    async def update_rule(
        self,
        rule_id: uuid.UUID,
        payload: RoutingRuleUpdate,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RoutingRuleRead:
        rule = await self.get_rule(rule_id)
        changes: dict[str, object] = {}
        if payload.name is not None and payload.name != rule.name:
            await self._assert_name_free(payload.name, exclude=rule.id)
            changes["name"] = {"from": rule.name, "to": payload.name}
            rule.name = payload.name
        if payload.strategy is not None and payload.strategy != rule.strategy:
            changes["strategy"] = {"from": rule.strategy.value, "to": payload.strategy.value}
            rule.strategy = payload.strategy
        if payload.match_conditions is not None:
            self._validate_conditions(payload.match_conditions)
            rule.match_conditions = payload.match_conditions
            changes["match_conditions"] = payload.match_conditions
        if payload.target_model_ids is not None:
            rule.target_model_ids = [str(item) for item in payload.target_model_ids]
            changes["target_model_ids"] = rule.target_model_ids
        if payload.fallback_chain is not None:
            rule.fallback_chain = [str(item) for item in payload.fallback_chain]
            changes["fallback_chain"] = rule.fallback_chain
        if payload.enabled is not None and payload.enabled != rule.enabled:
            rule.enabled = payload.enabled
            changes["enabled"] = payload.enabled
        if payload.priority is not None and payload.priority != rule.priority:
            rule.priority = payload.priority
            changes["priority"] = payload.priority

        if changes:
            await self.session.flush()
            await self.audit.record(
                AuditAction.ROUTING_RULE_UPDATED,
                actor=actor,
                entity_type="routing_rule",
                entity_id=str(rule.id),
                diff=changes,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return RoutingRuleRead.model_validate(rule)

    async def delete_rule(
        self,
        rule_id: uuid.UUID,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        rule = await self.get_rule(rule_id)
        await self.audit.record(
            AuditAction.ROUTING_RULE_DELETED,
            actor=actor,
            entity_type="routing_rule",
            entity_id=str(rule.id),
            diff={"name": rule.name, "strategy": rule.strategy.value},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.session.delete(rule)
        await self.session.flush()

    # -- decisions -----------------------------------------------------------
    async def matching_rule(self, *, model_name: str, model_id: uuid.UUID) -> RoutingRule | None:
        rows = (
            (
                await self.session.execute(
                    select(RoutingRule)
                    .where(RoutingRule.enabled.is_(True))
                    .order_by(RoutingRule.priority.asc(), RoutingRule.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        for rule in rows:
            if rule_matches(rule, model_name=model_name, model_id=model_id):
                return rule
        return None

    async def strategy_for(
        self,
        *,
        model_name: str,
        model_id: uuid.UUID | None = None,
        requested_strategy: RoutingStrategy | None = None,
    ) -> tuple[RoutingStrategy, RoutingRule | None]:
        if requested_strategy is not None:
            return requested_strategy, None
        rule = await self.matching_rule(model_name=model_name, model_id=model_id or uuid.uuid4())
        if rule is not None:
            return rule.strategy, rule
        return RoutingStrategy.PRIORITY, None

    async def decide(
        self,
        model_name: str,
        *,
        strategy: RoutingStrategy | None = None,
        offset: int = 0,
        candidates: list[Candidate] | None = None,
    ) -> tuple[list[tuple[Candidate, object]], RoutingStrategy, RoutingRule | None]:
        """Order the candidates that can serve ``model_name``.

        Returns ``(ordered, strategy, rule)`` where ``ordered`` is a list of
        ``(candidate, score)`` pairs — preferred candidates first, then the ones that
        only exist as a last resort (unhealthy, marked ineligible).
        """
        resolved = (
            candidates
            if candidates is not None
            else await resolve_candidates(self.session, model_name)
        )
        if not resolved:
            return [], strategy or RoutingStrategy.PRIORITY, None

        resolved_strategy, rule = await self.strategy_for(
            model_name=model_name,
            model_id=resolved[0].model.id,
            requested_strategy=strategy,
        )
        if rule is not None and rule.fallback_chain:
            preferred = [str(item) for item in rule.fallback_chain]
            resolved.sort(
                key=lambda candidate: (
                    0 if str(candidate.model.id) in preferred else 1,
                    preferred.index(str(candidate.model.id))
                    if str(candidate.model.id) in preferred
                    else 0,
                )
            )

        signals = await provider_signals(
            self.session, [candidate.provider.id for candidate in resolved]
        )
        scores = []
        by_key: dict[str, Candidate] = {}
        for candidate in resolved:
            signal = signals.get(candidate.provider.id)
            score = routing_engine.CandidateScore(
                key=candidate.key,
                score=0.0,
                health=signal.status if signal else None,
                latency_ms=signal.latency_ms if signal else None,
                price_per_1m=blended_price(candidate.model),
                payload={
                    "priority": candidate.provider.priority,
                    "weight": candidate.provider.weight,
                    "latency_source": signal.source if signal else "none",
                },
            )
            scores.append(score)
            by_key[candidate.key] = candidate

        decision = routing_engine.engine.rank(scores, resolved_strategy, offset=offset)
        ordered = [(by_key[item.key], item) for item in decision.ordered if item.key in by_key]
        return ordered, resolved_strategy, rule

    # -- simulation ----------------------------------------------------------
    async def simulate(
        self,
        *,
        model_name: str,
        strategy: RoutingStrategy | None = None,
        requested_tokens: int = 1000,
        offset: int | None = None,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
    ) -> RoutingSimulationResult:
        """Dry run: the same resolution and ordering the gateway uses, explained."""
        started = time.perf_counter()
        if offset is None:
            offset = await self._next_round_robin_offset(model_name, strategy)
        ordered, resolved_strategy, rule = await self.decide(
            model_name, strategy=strategy, offset=offset
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        candidates = [
            RoutingCandidate(
                model_id=candidate.model.id,
                model_name=candidate.model.name,
                provider_id=candidate.provider.id,
                provider_name=candidate.provider.name,
                credential_id=candidate.credential.id,
                endpoint_id=candidate.endpoint.id if candidate.endpoint else None,
                score=score.score,
                eligible=score.eligible,
                latency_ms=score.latency_ms,
                price_per_1m=score.price_per_1m,
                estimated_cost=(
                    (score.price_per_1m or 0) * requested_tokens / 1_000_000
                    if score.price_per_1m is not None
                    else None
                ),
                reasons=list(score.reasons),
            )
            for candidate, score in ordered
        ]
        selected = candidates[0] if candidates else None

        explanation = [
            f"strategy={resolved_strategy.value}",
            f"candidates={len(candidates)}",
            f"eligible={sum(1 for candidate in candidates if candidate.eligible)}",
            f"resolution_ms={elapsed_ms}",
        ]
        if rule is not None:
            explanation.append(f"rule={rule.name}")
        if requested_tokens:
            explanation.append(f"requested_tokens={requested_tokens}")
        if not candidates:
            explanation.append("no_candidate")

        if actor is not None:
            await self.audit.record(
                AuditAction.ROUTING_SIMULATED,
                actor=actor,
                entity_type="routing_rule",
                entity_id=str(rule.id) if rule else None,
                diff={
                    "model": model_name,
                    "strategy": resolved_strategy.value,
                    "candidates": len(candidates),
                    "selected_provider": selected.provider_name if selected else None,
                },
                ip_address=ip_address,
            )

        return RoutingSimulationResult(
            model=model_name,
            strategy=resolved_strategy,
            rule_id=rule.id if rule else None,
            rule_name=rule.name if rule else None,
            candidates=candidates,
            selected_model_id=selected.model_id if selected else None,
            selected_provider_id=selected.provider_id if selected else None,
            explanation=explanation,
        )

    async def _next_round_robin_offset(
        self, model_name: str, strategy: RoutingStrategy | None
    ) -> int:
        """Deterministic rotation for the simulator.

        The live gateway rotates in Redis (shared across workers); the simulator uses
        the attempt count of the model so two runs show the rotation an operator would
        actually observe, without depending on Redis being up.
        """
        resolved_strategy, rule = await self.strategy_for(
            model_name=model_name, requested_strategy=strategy
        )
        if resolved_strategy != RoutingStrategy.ROUND_ROBIN:
            return 0
        count = (
            await self.session.execute(
                select(func.count(UsageRecord.id))
                .join(Model, Model.id == UsageRecord.model_id)
                .where(Model.name == model_name)
            )
        ).scalar_one()
        return int(count or 0) if rule is None else int(count or 0)

    # -- helpers -------------------------------------------------------------
    async def _assert_name_free(self, name: str, *, exclude: uuid.UUID | None = None) -> None:
        statement = select(RoutingRule).where(func.lower(RoutingRule.name) == name.lower())
        if exclude is not None:
            statement = statement.where(RoutingRule.id != exclude)
        if (await self.session.execute(statement)).scalars().first() is not None:
            raise ConflictError(
                "A routing rule with this name already exists.", code="routing_rule_name_taken"
            )

    @staticmethod
    def _validate_conditions(conditions: dict | None) -> None:
        if conditions is None:
            return
        if not isinstance(conditions, dict):
            raise ValidationError(
                "Match conditions must be an object.",
                code="routing_conditions_invalid",
                details={"expected": "object"},
            )
        allowed = {"model", "api_key_id", "min_tokens", "max_tokens"}
        unknown = sorted(set(conditions) - allowed)
        if unknown:
            raise ValidationError(
                "One or more match conditions are not supported.",
                code="routing_conditions_invalid",
                details={"unknown": unknown, "allowed": sorted(allowed)},
            )


__all__ = [
    "Candidate",
    "ProviderSignal",
    "RoutingService",
    "blended_price",
    "credential_for",
    "first_endpoint",
    "provider_signals",
    "resolve_candidates",
    "rule_matches",
]
