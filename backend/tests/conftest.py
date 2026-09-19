"""Test configuration.

The suite runs against in-memory SQLite for speed; the environment variables must
be set before ``app`` is imported because settings are cached at import time.
PostgreSQL-only checks (migrations) are skipped unless a test database URL is
provided through ``XEREX_TEST_DATABASE_URL``.
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("XEREX_ENVIRONMENT", "test")
os.environ["XEREX_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["XEREX_REDIS_URL"] = "redis://127.0.0.1:6399/15"  # intentionally unreachable
os.environ["XEREX_RATE_LIMIT_ENABLED"] = "true"
os.environ["XEREX_SECRET_KEY"] = "test-secret-key-for-xerex-ai-suite"
os.environ["XEREX_LOG_LEVEL"] = "WARNING"
os.environ["XEREX_BOOTSTRAP_ENABLED"] = "true"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.enums import AdminRole, UserStatus  # noqa: E402
from app.models.identity import AdminUser  # noqa: E402

OWNER_EMAIL = "owner@xerex.ai"
OWNER_PASSWORD = "owner-password-123"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
async def session(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session


@pytest.fixture
async def app(engine, session_factory, monkeypatch):
    """FastAPI app wired to the in-memory database."""
    import app.database.session as db_session_module

    monkeypatch.setattr(db_session_module, "_engine", engine)
    monkeypatch.setattr(db_session_module, "_session_factory", session_factory)
    return create_app()


@pytest.fixture
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# --------------------------------------------------------------------------- #
# Factories
# --------------------------------------------------------------------------- #
async def create_user(
    session_factory,  # noqa: ANN001
    *,
    email: str | None = None,
    password: str | None = None,
    role: AdminRole = AdminRole.OWNER,
    status: UserStatus = UserStatus.ACTIVE,
) -> AdminUser:
    async with session_factory() as session:
        user = AdminUser(
            id=uuid.uuid4(),
            email=(email or OWNER_EMAIL),
            full_name="Test Administrator",
            password_hash=hash_password(password or OWNER_PASSWORD),
            role=role,
            status=status,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def login(
    client: AsyncClient, email: str = OWNER_EMAIL, password: str = OWNER_PASSWORD
) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["tokens"]["access_token"]


@pytest.fixture
async def owner(session_factory) -> AdminUser:
    return await create_user(session_factory)


@pytest.fixture
async def owner_headers(client: AsyncClient, owner: AdminUser) -> dict[str, str]:
    token = await login(client)
    return {"Authorization": f"Bearer {token}"}
