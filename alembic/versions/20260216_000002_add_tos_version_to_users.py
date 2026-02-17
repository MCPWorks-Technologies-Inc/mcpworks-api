"""Add tos_version to users table.

ORDER-008 (updated): Track which ToS version users accepted.

Revision ID: 20260216_000002
Revises: 20260216_000001
Create Date: 2026-02-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260216_000002"
down_revision: Union[str, None] = "20260216_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tos_version column to users table."""
    op.add_column(
        "users",
        sa.Column("tos_version", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    """Remove tos_version column from users table."""
    op.drop_column("users", "tos_version")
