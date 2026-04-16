"""Add cache_policy JSONB to functions for result caching configuration.

Revision ID: 20260415_000002
Revises: 20260415_000001
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260415_000002"
down_revision = "20260415_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "functions",
        sa.Column("cache_policy", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("functions", "cache_policy")
