"""Rate-limit abstraction (correction pass item 10).

The login limiter protects authentication; the gateway limiter (wiredup in M4)
enforces per-key limits on the public surface. This suite pins the guarantee that the
two never share configuration or namespace by accident, and that a per-key limit
overrides the deployment default only for that key.
"""

from __future__ import annotations

import pytest

from app.core.errors import DependencyUnavailableError
from app.services.rate_limit import (
    GATEWAY_SCOPE_KINDS,
    RateLimitPolicy,
    RateLimitScope,
    ScopedRateLimiter,
    gateway_limiter,
    gateway_rate_limit_policy,
    login_limiter,
)


def test_gateway_dimensions_are_declared() -> None:
    assert set(GATEWAY_SCOPE_KINDS) == {
        "api_key",
        "admin_user",
        "ip",
        "provider",
        "credential",
        "endpoint",
        "model",
        "plan",
    }
    assert "login" not in GATEWAY_SCOPE_KINDS  # the login scope is not a quota scope


def test_scope_keys_are_namespaced_per_dimension() -> None:
    keys = {
        RateLimitScope(kind=kind, identifier="abc").cache_key("xerex:ratelimit")
        for kind in GATEWAY_SCOPE_KINDS
    }
    assert len(keys) == len(GATEWAY_SCOPE_KINDS)
    assert "xerex:ratelimit:api_key:abc" in keys
    assert "xerex:ratelimit:plan:abc" in keys


def test_login_limiter_is_bound_to_its_own_policy_and_namespace() -> None:
    assert login_limiter.policy.scope_kind == "login"
    assert login_limiter.namespace == "xerex:ratelimit:login"
    assert (
        login_limiter.scope("127.0.0.1:owner@xerex.ai")
        .cache_key(login_limiter.namespace)
        .startswith("xerex:ratelimit:login:login:")
    )


def test_login_and_gateway_limiters_are_decoupled() -> None:
    assert login_limiter.namespace != gateway_limiter.namespace
    assert gateway_limiter.namespace == "xerex:ratelimit:gateway"
    assert gateway_limiter.policy.scope_kind == "api_key"
    assert login_limiter.policy.scope_kind == "login"


def test_gateway_limiter_uses_the_configured_default_window() -> None:
    from app.core.config import settings

    policy = gateway_rate_limit_policy()
    assert policy.limit == settings.gateway_default_rate_limit_per_min
    assert policy.window_seconds == 60


async def test_gateway_limiter_accepts_a_per_key_override() -> None:
    limiter = ScopedRateLimiter(policy_factory=gateway_rate_limit_policy)
    result = await limiter.hit("xrx_live_8f2a", limit=3, window_seconds=60, kind="api_key")
    assert result.limit == 3
    assert result.allowed is True


async def test_scoped_limiter_uses_the_policy_numbers_by_default() -> None:
    limiter = ScopedRateLimiter(
        policy=RateLimitPolicy(name="unit", scope_kind="ip", limit=7, window_seconds=30)
    )
    result = await limiter.hit("203.0.113.9")  # Redis is unreachable in the unit suite
    assert result.allowed is True
    assert result.backend == "bypassed"
    assert result.limit == 7


async def test_scoped_limiter_can_override_the_policy() -> None:
    limiter = ScopedRateLimiter(
        policy=RateLimitPolicy(name="unit", scope_kind="ip", limit=7, window_seconds=30)
    )
    result = await limiter.hit("203.0.113.9", limit=3, window_seconds=5, kind="api_key")
    assert result.limit == 3


async def test_require_exactly_one_policy_source() -> None:
    with pytest.raises(ValueError):
        ScopedRateLimiter()
    with pytest.raises(ValueError):
        ScopedRateLimiter(
            policy=RateLimitPolicy(name="a", scope_kind="ip", limit=1, window_seconds=1),
            policy_factory=lambda: RateLimitPolicy(
                name="b", scope_kind="ip", limit=1, window_seconds=1
            ),
        )


async def test_rate_limiting_can_be_disabled_entirely(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    limiter = ScopedRateLimiter(
        policy=RateLimitPolicy(name="unit", scope_kind="login", limit=1, window_seconds=1)
    )
    result = await limiter.hit("anything")
    assert result.backend == "bypassed"
    assert result.allowed is True


async def test_failure_is_fatal_when_redis_is_required(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "redis_required", True)
    limiter = ScopedRateLimiter(
        policy=RateLimitPolicy(name="unit", scope_kind="login", limit=1, window_seconds=1)
    )
    with pytest.raises(DependencyUnavailableError):
        await limiter.hit("anything")
