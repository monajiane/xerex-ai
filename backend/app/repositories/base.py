"""Generic repository helpers.

Route handlers never touch SQLAlchemy directly: they call services, and services
call repositories (see backend architecture in PROMPT.md).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- reads --------------------------------------------------------------
    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def get_by(self, **filters: Any) -> ModelT | None:
        result = await self.session.execute(self._filtered(select(self.model), **filters))
        return result.scalars().first()

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 25,
        order_by: Any = None,
        **filters: Any,
    ) -> Sequence[ModelT]:
        statement = self._filtered(select(self.model), **filters)
        if order_by is not None:
            statement = statement.order_by(order_by)
        statement = statement.offset(offset).limit(limit)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        statement = self._filtered(select(func.count()).select_from(self.model), **filters)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    # -- writes -------------------------------------------------------------
    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    # -- helpers ------------------------------------------------------------
    def _filtered(self, statement: Select, **filters: Any) -> Select:
        for field, value in filters.items():
            if value is None:
                continue
            column = getattr(self.model, field)
            if isinstance(value, (list, tuple, set)):
                statement = statement.where(column.in_(value))
            else:
                statement = statement.where(column == value)
        return statement
