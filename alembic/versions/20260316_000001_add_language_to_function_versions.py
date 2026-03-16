"""Add language column to function_versions.

Every function version now declares its programming language (python or
typescript).  Existing rows default to 'python' via server_default.

Revision ID: 20260316_000001
Revises: 20260315_000003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260316_000001"
down_revision: str | None = "20260315_000003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "function_versions",
        sa.Column("language", sa.String(20), nullable=False, server_default="python"),
    )


def downgrade() -> None:
    op.drop_column("function_versions", "language")
