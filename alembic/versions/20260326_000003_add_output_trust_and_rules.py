"""Add output_trust to functions and rules to namespace_mcp_servers.

Revision ID: 20260326_000003
Revises: 20260326_000002
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260326_000003"
down_revision = "20260326_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "functions",
        sa.Column(
            "output_trust",
            sa.String(10),
            nullable=False,
            server_default="prompt",
        ),
    )
    op.execute("UPDATE functions SET output_trust = 'prompt' WHERE output_trust IS NULL")
    op.alter_column("functions", "output_trust", server_default=None)

    op.add_column(
        "namespace_mcp_servers",
        sa.Column(
            "rules",
            postgresql.JSONB,
            nullable=False,
            server_default='{"request":[],"response":[]}',
        ),
    )


def downgrade() -> None:
    op.drop_column("namespace_mcp_servers", "rules")
    op.drop_column("functions", "output_trust")
