"""Portable column types.

The platform targets PostgreSQL (JSONB) but the test-suite runs on SQLite, so
JSON columns are declared through a variant-aware alias.
"""

from __future__ import annotations

from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import JSONB

#: JSON column that uses JSONB on PostgreSQL and JSON elsewhere (SQLite tests).
JsonColumn = JSON().with_variant(JSONB(), "postgresql")

__all__ = ["JSONB", "JsonColumn", "Uuid"]
