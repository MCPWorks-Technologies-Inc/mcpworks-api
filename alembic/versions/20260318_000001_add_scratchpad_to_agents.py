"""Add scratchpad columns to agents.

Per-agent visual scratchpad: HTML/JS/CSS served at a secret URL.
Adds token (for URL auth), size tracking, and last-update timestamp.

Revision ID: 20260318_000001
Revises: 20260316_000001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260318_000001"
down_revision: str | None = "20260316_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("scratchpad_token", sa.String(64), nullable=True))
    op.add_column(
        "agents",
        sa.Column("scratchpad_size_bytes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agents",
        sa.Column("scratchpad_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agents_scratchpad_token",
        "agents",
        ["scratchpad_token"],
        unique=True,
        postgresql_where=sa.text("scratchpad_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_agents_scratchpad_token", table_name="agents")
    op.drop_column("agents", "scratchpad_updated_at")
    op.drop_column("agents", "scratchpad_size_bytes")
    op.drop_column("agents", "scratchpad_token")
