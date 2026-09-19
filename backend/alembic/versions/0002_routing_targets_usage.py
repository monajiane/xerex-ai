"""Endpoint credentials, typed health targets and per-attempt usage

Revision ID: 0002_routing_targets_usage
Revises: 0001_initial_schema
Create Date: 2026-09-18 17:05:00.000000

Correction pass before M2. Three additive changes, no destructive rewrite:

1. ``model_endpoints.credential_id`` and ``model_endpoints.provider_id`` — an
   endpoint can be bound to a specific credential and/or a different provider than
   the model's home provider, so a routing engine can fail over across credentials
   *and* endpoints. Both nullable, ``ON DELETE SET NULL``.
2. ``health_checks`` gains typed ``provider_id`` / ``credential_id`` /
   ``model_id`` / ``endpoint_id`` columns next to the polymorphic
   ``target_type``/``target_id`` pointer, giving real foreign keys and indexes.
3. ``client_requests`` — one row per downstream request — plus attempt columns on
   ``usage_records`` (``client_request_id``, ``attempt_number``, ``is_final``,
   ``retryable``, ``credential_id``, ``endpoint_id``). ``request_id`` stops being
   unique because several attempts share one client request id.

Existing M1 rows stay valid: every new column is nullable or has a temporary
server default that is dropped again in the same migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_routing_targets_usage"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CLIENT_REQUEST_STATE = sa.Enum(
    "pending",
    "succeeded",
    "failed",
    name="client_request_state",
    native_enum=False,
    length=32,
)

_HEALTH_TARGETS: tuple[tuple[str, str], ...] = (
    ("provider_id", "providers"),
    ("credential_id", "provider_credentials"),
    ("model_id", "models"),
    ("endpoint_id", "model_endpoints"),
)


def _dialect() -> str:
    return op.get_bind().dialect.name


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Endpoint -> credential binding
    # ------------------------------------------------------------------ #
    op.add_column("model_endpoints", sa.Column("credential_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_model_endpoints_credential_id"),
        "model_endpoints",
        ["credential_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_model_endpoints_credential_id_provider_credentials"),
        "model_endpoints",
        "provider_credentials",
        ["credential_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Optional provider override: lets one endpoint of a model be reached through a
    # different provider than the model's home provider.
    op.add_column("model_endpoints", sa.Column("provider_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_model_endpoints_provider_id"), "model_endpoints", ["provider_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_model_endpoints_provider_id_providers"),
        "model_endpoints",
        "providers",
        ["provider_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------------ #
    # 2. Typed health targets
    # ------------------------------------------------------------------ #
    for column, table in _HEALTH_TARGETS:
        op.add_column("health_checks", sa.Column(column, sa.Uuid(), nullable=True))
        op.create_index(op.f(f"ix_health_checks_{column}"), "health_checks", [column], unique=False)
        op.create_foreign_key(
            op.f(f"fk_health_checks_{column}_{table}"),
            "health_checks",
            table,
            [column],
            ["id"],
            ondelete="SET NULL",
        )

    # ------------------------------------------------------------------ #
    # 3. Client requests and per-attempt usage
    # ------------------------------------------------------------------ #
    op.create_table(
        "client_requests",
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("api_key_id", sa.Uuid(), nullable=True),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column("requested_model", sa.String(length=160), nullable=True),
        sa.Column("streaming", sa.Boolean(), nullable=False),
        sa.Column("state", _CLIENT_REQUEST_STATE, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("final_status_code", sa.Integer(), nullable=True),
        sa.Column("final_error_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.id"],
            name=op.f("fk_client_requests_admin_user_id_admin_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["api_keys.id"],
            name=op.f("fk_client_requests_api_key_id_api_keys"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_requests")),
    )
    op.create_index(
        op.f("ix_client_requests_request_id"), "client_requests", ["request_id"], unique=True
    )
    op.create_index(
        op.f("ix_client_requests_admin_user_id"),
        "client_requests",
        ["admin_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_requests_api_key_id"), "client_requests", ["api_key_id"], unique=False
    )
    op.create_index(op.f("ix_client_requests_state"), "client_requests", ["state"], unique=False)
    op.create_index(
        op.f("ix_client_requests_started_at"), "client_requests", ["started_at"], unique=False
    )

    # usage_records becomes the per-attempt ledger ------------------------
    op.drop_index(op.f("ix_usage_records_request_id"), table_name="usage_records")
    op.create_index(
        op.f("ix_usage_records_request_id"), "usage_records", ["request_id"], unique=False
    )

    op.add_column("usage_records", sa.Column("client_request_id", sa.Uuid(), nullable=True))
    op.add_column(
        "usage_records",
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "usage_records",
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "usage_records",
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("usage_records", sa.Column("credential_id", sa.Uuid(), nullable=True))
    op.add_column("usage_records", sa.Column("endpoint_id", sa.Uuid(), nullable=True))

    # The temporary defaults only exist to satisfy NOT NULL on existing rows.
    if _dialect() != "sqlite":
        for column in ("attempt_number", "is_final", "retryable"):
            op.alter_column("usage_records", column, server_default=None)

    op.create_index(
        op.f("ix_usage_records_client_request_id"),
        "usage_records",
        ["client_request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_usage_records_credential_id"), "usage_records", ["credential_id"], unique=False
    )
    op.create_index(
        op.f("ix_usage_records_endpoint_id"), "usage_records", ["endpoint_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_usage_records_client_request_id_client_requests"),
        "usage_records",
        "client_requests",
        ["client_request_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_usage_records_credential_id_provider_credentials"),
        "usage_records",
        "provider_credentials",
        ["credential_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_usage_records_endpoint_id_model_endpoints"),
        "usage_records",
        "model_endpoints",
        ["endpoint_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_usage_records_attempt_number",
        "usage_records",
        ["client_request_id", "attempt_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_usage_records_attempt_number", "usage_records", type_="unique")
    op.drop_constraint(
        op.f("fk_usage_records_endpoint_id_model_endpoints"), "usage_records", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_usage_records_credential_id_provider_credentials"),
        "usage_records",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_usage_records_client_request_id_client_requests"),
        "usage_records",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_usage_records_endpoint_id"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_credential_id"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_client_request_id"), table_name="usage_records")
    op.drop_column("usage_records", "endpoint_id")
    op.drop_column("usage_records", "credential_id")
    op.drop_column("usage_records", "retryable")
    op.drop_column("usage_records", "is_final")
    op.drop_column("usage_records", "attempt_number")
    op.drop_column("usage_records", "client_request_id")

    op.drop_index(op.f("ix_usage_records_request_id"), table_name="usage_records")
    op.create_index(
        op.f("ix_usage_records_request_id"), "usage_records", ["request_id"], unique=True
    )

    op.drop_index(op.f("ix_client_requests_request_id"), table_name="client_requests")
    op.drop_index(op.f("ix_client_requests_started_at"), table_name="client_requests")
    op.drop_index(op.f("ix_client_requests_state"), table_name="client_requests")
    op.drop_index(op.f("ix_client_requests_api_key_id"), table_name="client_requests")
    op.drop_index(op.f("ix_client_requests_admin_user_id"), table_name="client_requests")
    op.drop_table("client_requests")

    for column, _table in reversed(_HEALTH_TARGETS):
        op.drop_constraint(
            op.f(f"fk_health_checks_{column}_{_table}"), "health_checks", type_="foreignkey"
        )
        op.drop_index(op.f(f"ix_health_checks_{column}"), table_name="health_checks")
        op.drop_column("health_checks", column)

    op.drop_constraint(
        op.f("fk_model_endpoints_provider_id_providers"), "model_endpoints", type_="foreignkey"
    )
    op.drop_index(op.f("ix_model_endpoints_provider_id"), table_name="model_endpoints")
    op.drop_column("model_endpoints", "provider_id")
    op.drop_constraint(
        op.f("fk_model_endpoints_credential_id_provider_credentials"),
        "model_endpoints",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_model_endpoints_credential_id"), table_name="model_endpoints")
    op.drop_column("model_endpoints", "credential_id")
