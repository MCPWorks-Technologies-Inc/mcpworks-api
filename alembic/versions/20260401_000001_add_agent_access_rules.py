"""Add access_rules JSONB column to agents table.

Revision ID: 20260401_000001
Revises: 20260329_000001
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260401_000001"
down_revision = "20260329_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("access_rules", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "access_rules")
