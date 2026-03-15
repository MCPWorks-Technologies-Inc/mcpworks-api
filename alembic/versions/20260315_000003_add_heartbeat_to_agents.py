"""Add heartbeat columns to agents.

Heartbeat mode: proactive autonomy loop where the agent wakes on a
configurable interval and its AI decides whether to act.

Revision ID: 20260315_000003
Revises: 20260315_000002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260315_000003"
down_revision: str | None = "20260315_000002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("heartbeat_interval", sa.Integer(), nullable=True))
    op.add_column(
        "agents",
        sa.Column("heartbeat_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "agents",
        sa.Column("heartbeat_next_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "heartbeat_next_at")
    op.drop_column("agents", "heartbeat_enabled")
    op.drop_column("agents", "heartbeat_interval")
