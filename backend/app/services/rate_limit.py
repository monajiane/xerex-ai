"""Redis-backed fixed-window rate limiting.

Used from M1 to protect the login endpoint; the same primitive is reused by the
gateway for per-API-key limits in M4. When Redis is unavailable the limiter
fails open (unless ``XEREX_REDIS_REQUIRED`` is set) so the admin panel keeps
working in a degraded deployment.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger
from app.database.redis import get_redis

logger = get_logger(__name__)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int
    limit: int
    backend: str  # "redis" | "bypassed"


class RateLimiter:
    def __init__(self, *, prefix: str = "xerex:ratelimit") -> None:
        self.prefix = prefix

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        if not settings.rate_limit_enabled:
            return RateLimitResult(True, limit, 0, limit, "bypassed")
        redis_key = f"{self.prefix}:{key}"
        try:
            client = get_redis()
            pipe = client.pipeline()
            pipe.incr(redis_key)
            pipe.ttl(redis_key)
            count, ttl = await pipe.execute()
            if ttl is None or int(ttl) < 0:
                await client.expire(redis_key, window_seconds)
                ttl = window_seconds
            current = int(count)
            allowed = current <= limit
            return RateLimitResult(
                allowed=allowed,
                remaining=max(limit - current, 0),
                retry_after_seconds=0 if allowed else int(ttl),
                limit=limit,
                backend="redis",
            )
        except (RedisError, OSError) as exc:
            logger.warning("rate_limit_backend_unavailable", extra={"error": type(exc).__name__})
            return RateLimitResult(True, limit, 0, limit, "bypassed")

    async def reset(self, key: str) -> None:
        try:
            await get_redis().delete(f"{self.prefix}:{key}")
        except (RedisError, OSError):
            logger.debug("rate_limit_reset_skipped", exc_info=True)


login_limiter = RateLimiter(prefix="xerex:ratelimit:login")
