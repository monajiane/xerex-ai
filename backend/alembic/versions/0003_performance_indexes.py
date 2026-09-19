"""Performance indexes for the M6 analytics and request-log screens

Revision ID: 0003_performance_indexes
Revises: 0002_routing_targets_usage
Create Date: 2026-09-19 11:20:00.000000

M6 turned ``usage_records`` into the source of every dashboard, «مصرف» and
«گزارش درخواست‌ها» number, so the access patterns deserve explicit indexes instead of
sequential scans on a growing ledger. Purely additive; ``downgrade`` restores exactly the
previous index definitions.

1. ``usage_records (created_at, id)`` — the window filter of every aggregate, with the id
   appended so the index can serve counting without a table lookup.
2. ``usage_records (client_request_id) WHERE is_final`` — the final-attempt subquery of
   the request log joins on that predicate; a partial index stays small because a request
   has exactly one final attempt. Supported by both PostgreSQL and SQLite.
3. ``client_requests (started_at, state)`` — the reverse-chronological log list with its
   most common filter, so filtering by outcome does not force a separate sort.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_performance_indexes"
down_revision: str | None = "0002_routing_targets_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IS_FINAL = sa.text("is_final")


def upgrade() -> None:
    op.drop_index(op.f("ix_usage_records_created_at"), table_name="usage_records")
    op.create_index(
        op.f("ix_usage_records_created_at"),
        "usage_records",
        ["created_at", "id"],
        unique=False,
    )

    op.create_index(
        "ix_usage_records_final_attempt",
        "usage_records",
        ["client_request_id"],
        unique=False,
        postgresql_where=_IS_FINAL,
        sqlite_where=_IS_FINAL,
    )

    op.drop_index(op.f("ix_client_requests_started_at"), table_name="client_requests")
    op.create_index(
        op.f("ix_client_requests_started_at"),
        "client_requests",
        ["started_at", "state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_client_requests_started_at"), table_name="client_requests")
    op.create_index(
        op.f("ix_client_requests_started_at"),
        "client_requests",
        ["started_at"],
        unique=False,
    )

    op.drop_index("ix_usage_records_final_attempt", table_name="usage_records")

    op.drop_index(op.f("ix_usage_records_created_at"), table_name="usage_records")
    op.create_index(
        op.f("ix_usage_records_created_at"),
        "usage_records",
        ["created_at"],
        unique=False,
    )
