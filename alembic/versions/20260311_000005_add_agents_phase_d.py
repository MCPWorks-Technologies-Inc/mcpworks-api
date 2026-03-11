"""Add agents phase D: agent_channels table

Revision ID: 20260311_000005
Revises: 20260311_000004
Create Date: 2026-03-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260311_000005"
down_revision: str = "20260311_000004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("config_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("config_dek_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("agent_id", "channel_type", name="uq_agent_channel_type"),
    )
    op.create_index("ix_agent_channels_agent_id", "agent_channels", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_channels_agent_id", table_name="agent_channels")
    op.drop_table("agent_channels")
