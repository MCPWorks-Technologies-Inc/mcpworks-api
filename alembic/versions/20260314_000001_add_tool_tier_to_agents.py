"""Add tool_tier and scheduled_tool_tier to agents

Revision ID: 20260314_000001
Revises: 20260313_000001
Create Date: 2026-03-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260314_000001"
down_revision: str | None = "20260313_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("tool_tier", sa.String(20), nullable=False, server_default="standard"),
    )
    op.add_column(
        "agents",
        sa.Column(
            "scheduled_tool_tier", sa.String(20), nullable=False, server_default="execute_only"
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "scheduled_tool_tier")
    op.drop_column("agents", "tool_tier")
