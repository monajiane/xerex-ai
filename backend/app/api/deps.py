"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_db_session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(db_session)]


class Pagination:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="1-based page number.")] = 1,
        page_size: Annotated[int, Query(ge=1, le=200, description="Items per page.")] = 25,
        search: Annotated[
            str | None, Query(max_length=120, description="Free text search.")
        ] = None,
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.search = search

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


PaginationDep = Annotated[Pagination, Depends(Pagination)]
