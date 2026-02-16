"""Add tos_accepted_at to users table.

ORDER-008: Track when users accept Terms of Service.

Revision ID: 20260216_000001
Revises: 20260215_000001
Create Date: 2026-02-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260216_000001"
down_revision: Union[str, None] = "20260215_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tos_accepted_at column to users table."""
    op.add_column(
        "users",
        sa.Column("tos_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove tos_accepted_at column from users table."""
    op.drop_column("users", "tos_accepted_at")
