"""Add deleted_at soft-delete column to functions.

Enables soft-delete: deleted functions keep their version history so
re-creation with the same name continues the version sequence.

Revision ID: 20260319_000001
Revises: 20260318_000001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260319_000001"
down_revision: str | None = "20260318_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "functions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_functions_deleted_at", "functions", ["deleted_at"])

    op.drop_constraint("uq_function_service_name", "functions", type_="unique")
    op.create_index(
        "uq_function_service_name_active",
        "functions",
        ["service_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_function_service_name_active", table_name="functions")
    op.create_unique_constraint("uq_function_service_name", "functions", ["service_id", "name"])
    op.drop_index("ix_functions_deleted_at", table_name="functions")
    op.drop_column("functions", "deleted_at")
