"""Add required_env and optional_env columns to function_versions

Allow functions to declare which environment variables they need.
Names only — values are NEVER stored server-side.

Revision ID: 20260219_000001
Revises: 20260217_000002
Create Date: 2026-02-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260219_000001"
down_revision: str | None = "20260217_000002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "function_versions",
        sa.Column(
            "required_env",
            sa.ARRAY(sa.String()),
            nullable=True,
        ),
    )
    op.add_column(
        "function_versions",
        sa.Column(
            "optional_env",
            sa.ARRAY(sa.String()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("function_versions", "optional_env")
    op.drop_column("function_versions", "required_env")
