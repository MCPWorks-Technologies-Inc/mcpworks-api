"""Add soft-delete support to namespaces.

Adds deleted_at column and partial indexes for efficient querying
of active vs soft-deleted namespaces.

Revision ID: 20260302_000001
Revises: 20260301_000003
Create Date: 2026-03-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260302_000001"
down_revision: str | None = "20260301_000003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "namespaces",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_namespaces_active_name",
        "namespaces",
        ["name"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_namespaces_deleted_at",
        "namespaces",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_namespaces_deleted_at", table_name="namespaces")
    op.drop_index("ix_namespaces_active_name", table_name="namespaces")
    op.drop_column("namespaces", "deleted_at")
