"""Async engine, session factory and database health probe."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        connect_args = settings.database_connect_args() if not settings.is_sqlite else {}
        kwargs: dict[str, object] = {
            "echo": settings.database_echo,
            "pool_pre_ping": True,
            "future": True,
        }
        if not settings.is_sqlite:
            kwargs.update(
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
            )
        _engine = create_async_engine(settings.database_url, connect_args=connect_args, **kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False
        )
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Session for background jobs and non-request code."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency implementing one transaction per request.

    The unit of work is committed when the request completes successfully and
    rolled back on any exception, so services never commit on their own.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database() -> dict[str, object]:
    """Returns a component health payload (English keys)."""
    started = time.perf_counter()
    probe = "select sqlite_version()" if settings.is_sqlite else "select version()"
    try:
        async with get_engine().connect() as connection:
            result = await connection.execute(text(probe))
            version_row = result.scalar_one_or_none()
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        version = str(version_row).split(",")[0] if version_row else "unknown"
        return {
            "name": "database",
            "status": "healthy",
            "latency_ms": latency_ms,
            "dialect": "sqlite" if settings.is_sqlite else "postgresql",
            "version": version,
        }
    except Exception as exc:  # noqa: BLE001 - reported as a component status
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.warning("database_health_failed", extra={"error": str(exc)})
        return {
            "name": "database",
            "status": "down",
            "latency_ms": latency_ms,
            "dialect": "sqlite" if settings.is_sqlite else "postgresql",
            "error": type(exc).__name__,
        }


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
