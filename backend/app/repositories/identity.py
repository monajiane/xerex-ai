"""Repositories for administrator identity."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models.identity import AdminUser, RefreshToken
from app.repositories.base import BaseRepository


class AdminUserRepository(BaseRepository[AdminUser]):
    model = AdminUser

    async def get_by_email(self, email: str) -> AdminUser | None:
        statement = select(AdminUser).where(func.lower(AdminUser.email) == email.strip().lower())
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(AdminUser))
        return int(result.scalar_one())


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        statement = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)
        await self.session.flush()

    async def revoke_all_for_user(self, user_id) -> int:  # noqa: ANN001 - uuid.UUID
        statement = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        result = await self.session.execute(statement)
        tokens = result.scalars().all()
        now = datetime.now(UTC)
        for token in tokens:
            token.revoked_at = now
        await self.session.flush()
        return len(tokens)
