"""Add chat_token to agents.

Public chat endpoint authentication via obfuscated URL token.
Pattern: POST https://{agent}.agent.mcpworks.io/chat/{token}

Revision ID: 20260319_000003
Revises: 20260319_000002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "20260319_000003"
down_revision: str | None = "20260319_000002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("chat_token", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_agents_chat_token",
        "agents",
        ["chat_token"],
        unique=True,
        postgresql_where=text("chat_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_agents_chat_token", table_name="agents")
    op.drop_column("agents", "chat_token")
