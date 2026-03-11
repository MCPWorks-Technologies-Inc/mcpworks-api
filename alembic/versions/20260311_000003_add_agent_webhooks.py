"""Add agent_webhooks table

Revision ID: 20260311_000003
Revises: 20260311_000002
Create Date: 2026-03-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260311_000003"
down_revision: str = "20260311_000002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("handler_function_name", sa.String(255), nullable=False),
        sa.Column("secret_hash", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("agent_id", "path", name="uq_agent_webhook_path"),
    )
    op.create_index("ix_agent_webhooks_agent_id", "agent_webhooks", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_webhooks_agent_id", table_name="agent_webhooks")
    op.drop_table("agent_webhooks")
