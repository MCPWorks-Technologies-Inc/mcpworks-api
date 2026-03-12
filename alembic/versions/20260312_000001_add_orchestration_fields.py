"""Add orchestration_mode to schedules/webhooks and auto_channel to agents

Revision ID: 20260312_000001
Revises: 20260311_000006
Create Date: 2026-03-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260312_000001"
down_revision: str = "20260311_000006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_schedules",
        sa.Column("orchestration_mode", sa.String(20), nullable=False, server_default="direct"),
    )
    op.add_column(
        "agent_webhooks",
        sa.Column("orchestration_mode", sa.String(20), nullable=False, server_default="direct"),
    )
    op.add_column(
        "agents",
        sa.Column("auto_channel", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "auto_channel")
    op.drop_column("agent_webhooks", "orchestration_mode")
    op.drop_column("agent_schedules", "orchestration_mode")
