"""Redis client and health probe.

Foundation for rate limiting, caching, distributed locks, background jobs and
health monitoring (PROMPT.md section: Redis). The API degrades gracefully when
Redis is unreachable and ``XEREX_REDIS_REQUIRED`` is false.

Authentication is configured through the environment: either credentials inside
``XEREX_REDIS_URL`` or the dedicated ``XEREX_REDIS_USERNAME`` /
``XEREX_REDIS_PASSWORD`` pair (see :meth:`Settings.redis_connection_url`). No
password is ever hard-coded here.
"""

from __future__ import annotations

import time
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: aioredis.Redis | None = None
_last_error: str | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_connection_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=settings.redis_socket_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
            health_check_interval=15,
        )
    return _client


async def check_redis() -> dict[str, Any]:
    global _last_error
    started = time.perf_counter()
    try:
        client = get_redis()
        pong = await client.ping()
        info = await client.info(section="server")
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _last_error = None
        return {
            "name": "redis",
            "status": "healthy" if pong else "degraded",
            "latency_ms": latency_ms,
            "version": info.get("redis_version", "unknown"),
            "required": settings.redis_required,
        }
    except (RedisError, OSError) as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _last_error = f"{type(exc).__name__}: {exc}"
        logger.warning("redis_health_failed", extra={"error": _last_error})
        return {
            "name": "redis",
            "status": "down" if settings.redis_required else "degraded",
            "latency_ms": latency_ms,
            "required": settings.redis_required,
            "error": type(exc).__name__,
            "degraded_ok": not settings.redis_required,
        }


def redis_last_error() -> str | None:
    return _last_error


async def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            logger.debug("redis_close_failed", exc_info=True)
        _client = None
