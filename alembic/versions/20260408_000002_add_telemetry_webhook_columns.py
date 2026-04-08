"""Add telemetry webhook columns to namespaces.

Revision ID: 20260408_000002
Revises: 20260408_000001
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260408_000002"
down_revision = "20260408_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("namespaces", sa.Column("telemetry_webhook_url", sa.Text, nullable=True))
    op.add_column(
        "namespaces",
        sa.Column("telemetry_webhook_secret_encrypted", sa.LargeBinary, nullable=True),
    )
    op.add_column(
        "namespaces",
        sa.Column("telemetry_webhook_secret_dek", sa.LargeBinary, nullable=True),
    )
    op.add_column(
        "namespaces",
        sa.Column("telemetry_config", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("namespaces", "telemetry_config")
    op.drop_column("namespaces", "telemetry_webhook_secret_dek")
    op.drop_column("namespaces", "telemetry_webhook_secret_encrypted")
    op.drop_column("namespaces", "telemetry_webhook_url")
