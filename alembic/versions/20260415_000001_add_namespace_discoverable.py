"""Add discoverable boolean to namespaces for .well-known server card listing.

Revision ID: 20260415_000001
Revises: 20260414_000001
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260415_000001"
down_revision = "20260414_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "namespaces",
        sa.Column("discoverable", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("namespaces", "discoverable")
