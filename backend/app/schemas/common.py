"""Shared response envelopes and pagination primitives."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ErrorDetail(ApiModel):
    code: str = Field(description="Stable English machine-readable error code.")
    message: str = Field(description="English developer-facing message.")
    request_id: str | None = None
    details: dict | None = None


class ErrorEnvelope(ApiModel):
    error: ErrorDetail


class PageParams(ApiModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page(ApiModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return math.ceil(self.total / self.page_size) if self.page_size else 0

    @classmethod
    def build(cls, items: list[T], total: int, params: PageParams) -> Page[T]:
        return cls(items=items, total=total, page=params.page, page_size=params.page_size)


class TimestampedRead(ApiModel):
    created_at: datetime
    updated_at: datetime | None = None


class MessageResponse(ApiModel):
    """English internal acknowledgement; the UI renders its own Persian copy."""

    status: str = "ok"
