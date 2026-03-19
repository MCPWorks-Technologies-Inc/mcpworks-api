"""Add scratchpad_expires_at to agents.

Tier-based TTL for scratchpad content. Pro: 7 days, Enterprise: 30 days.
Timer resets on each publish/append. Expired views return 410 Gone.

Revision ID: 20260319_000002
Revises: 20260319_000001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260319_000002"
down_revision: str | None = "20260319_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("scratchpad_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "scratchpad_expires_at")
