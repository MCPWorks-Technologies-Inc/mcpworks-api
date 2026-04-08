"""Add input_bytes column to mcp_execution_stats.

Revision ID: 20260408_000001
Revises: 20260407_000002
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "20260408_000001"
down_revision = "20260407_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_execution_stats",
        sa.Column("input_bytes", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("mcp_execution_stats", "input_bytes")
