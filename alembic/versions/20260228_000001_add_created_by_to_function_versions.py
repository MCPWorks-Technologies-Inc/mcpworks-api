"""Add created_by column to function_versions

Allow tracking who created each function version (e.g. 'Claude Opus 4.6').

Revision ID: 20260228_000001
Revises: 20260225_000003
Create Date: 2026-02-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260228_000001"
down_revision: str | None = "20260225_000003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "function_versions",
        sa.Column(
            "created_by",
            sa.String(100),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("function_versions", "created_by")
