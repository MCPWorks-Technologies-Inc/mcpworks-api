"""Add scanner_pipeline JSONB column to namespaces table.

Revision ID: 20260407_000002
Revises: 20260407_000001
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260407_000002"
down_revision = "20260407_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("namespaces", sa.Column("scanner_pipeline", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("namespaces", "scanner_pipeline")
