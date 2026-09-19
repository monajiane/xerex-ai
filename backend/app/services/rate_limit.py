"""Redis-backed rate limiting: one policy-driven limiter, many scopes.

Architecture note (this is the point of the module):

* :class:`RateLimitScope` names *what* a limit applies to. M1 only uses ``login``,
  but the gateway in M4 will need the same primitive per API key, administrator,
  IP, provider, credential, endpoint, model and plan/quota. Those dimensions are
  declared in :data:`GATEWAY_SCOPE_KINDS` so no redesign is required later.
* :class:`RateLimitPolicy` carries the numbers (limit, window, fail mode) so the
  login limiter and the future gateway limiter are configured separately and never
  share state or configuration by accident.
* :class:`ScopedRateLimiter` is the reusable engine. ``login_limiter`` and
  ``gateway_limiter`` are two bound instances with their own policies and namespaces.
  M4 wires ``gateway_limiter`` into the public ``/v1`` surface, where the per-key
  ``rate_limit_per_min`` overrides the default limit for that key only.

When Redis is unavailable the limiter fails open unless ``XEREX_REDIS_REQUIRED``
is set, in which case the request fails with ``dependency_unavailable`` instead of
silently disabling protection.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger
from app.database.redis import get_redis

logger = get_logger(__name__)

#: Dimensions a limit can be bound to. ``login`` is the M1 scope; the rest are the
#: gateway dimensions announced for M4/M5.
ScopeKind = Literal[
    "login",
    "api_key",
    "admin_user",
    "ip",
    "provider",
    "credential",
    "endpoint",
    "model",
    "plan",
]

GATEWAY_SCOPE_KINDS: tuple[ScopeKind, ...] = (
    "api_key",
    "admin_user",
    "ip",
    "provider",
    "credential",
    "endpoint",
    "model",
    "plan",
)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int
    limit: int
    backend: str  # "redis" | "bypassed"


@dataclass(frozen=True)
class RateLimitScope:
    """A single dimension instance, e.g. ``api_key:xrx_live_8f2a``."""

    kind: ScopeKind
    identifier: str

    def cache_key(self, namespace: str) -> str:
        return f"{namespace}:{self.kind}:{self.identifier}"


@dataclass(frozen=True)
class RateLimitPolicy:
    """Numbers and behaviour for one limiter instance."""

    name: str
    scope_kind: ScopeKind
    limit: int
    window_seconds: int


def gateway_rate_limit_policy() -> RateLimitPolicy:
    """Default policy for the public gateway.

    The effective limit for a call is the key's own ``rate_limit_per_min``; this
    factory provides the deployment default and the window, so a key without an
    explicit value still has a limit that an operator can change without a release.
    """
    return RateLimitPolicy(
        name="gateway_rate_limit",
        scope_kind="api_key",
        limit=settings.gateway_default_rate_limit_per_min,
        window_seconds=60,
    )


def login_rate_limit_policy() -> RateLimitPolicy:
    """Login policy, read from settings on every call so it stays runtime-configurable."""
    return RateLimitPolicy(
        name="login_rate_limit",
        scope_kind="login",
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )


class ScopedRateLimiter:
    """Fixed-window counter limiter bound to one policy and namespace."""

    def __init__(
        self,
        *,
        policy: RateLimitPolicy | None = None,
        policy_factory: Callable[[], RateLimitPolicy] | None = None,
        namespace: str = "xerex:ratelimit",
    ) -> None:
        if (policy is None) == (policy_factory is None):
            raise ValueError("provide exactly one of policy or policy_factory")
        self._policy = policy
        self._policy_factory = policy_factory
        self.namespace = namespace

    @property
    def policy(self) -> RateLimitPolicy:
        return self._policy if self._policy is not None else self._policy_factory()  # type: ignore[misc]

    def scope(self, identifier: str, *, kind: ScopeKind | None = None) -> RateLimitScope:
        return RateLimitScope(kind=kind or self.policy.scope_kind, identifier=identifier)

    async def hit(
        self,
        identifier: str,
        *,
        limit: int | None = None,
        window_seconds: int | None = None,
        kind: ScopeKind | None = None,
    ) -> RateLimitResult:
        policy = self.policy
        effective_limit = limit if limit is not None else policy.limit
        effective_window = window_seconds if window_seconds is not None else policy.window_seconds
        scope = self.scope(identifier, kind=kind)
        redis_key = scope.cache_key(self.namespace)

        if not settings.rate_limit_enabled:
            return RateLimitResult(True, effective_limit, 0, effective_limit, "bypassed")
        try:
            client = get_redis()
            pipe = client.pipeline()
            pipe.incr(redis_key)
            pipe.ttl(redis_key)
            count, ttl = await pipe.execute()
            if ttl is None or int(ttl) < 0:
                await client.expire(redis_key, effective_window)
                ttl = effective_window
            current = int(count)
            allowed = current <= effective_limit
            return RateLimitResult(
                allowed=allowed,
                remaining=max(effective_limit - current, 0),
                retry_after_seconds=0 if allowed else int(ttl),
                limit=effective_limit,
                backend="redis",
            )
        except (RedisError, OSError) as exc:
            logger.warning("rate_limit_backend_unavailable", extra={"error": type(exc).__name__})
            if settings.redis_required:
                raise DependencyUnavailableError(
                    "The rate limiting backend is unavailable.",
                    details={"component": "redis", "policy": policy.name},
                ) from exc
            return RateLimitResult(True, effective_limit, 0, effective_limit, "bypassed")

    async def reset(self, identifier: str, *, kind: ScopeKind | None = None) -> None:
        scope = self.scope(identifier, kind=kind)
        try:
            await get_redis().delete(scope.cache_key(self.namespace))
        except (RedisError, OSError):
            logger.debug("rate_limit_reset_skipped", exc_info=True)


#: Protects the login endpoint. Keys look like
#: ``xerex:ratelimit:login:login:<ip>:<email>``.
login_limiter = ScopedRateLimiter(
    policy_factory=login_rate_limit_policy,
    namespace="xerex:ratelimit:login",
)

#: Enforces the per-key limits of the public gateway (M4). Keys look like
#: ``xerex:ratelimit:gateway:api_key:xrx_live_8f2a``.
gateway_limiter = ScopedRateLimiter(
    policy_factory=gateway_rate_limit_policy,
    namespace="xerex:ratelimit:gateway",
)
