"""Create email_logs table

Revision ID: 20260225_000003
Revises: 20260225_000002
Create Date: 2026-02-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "20260225_000003"
down_revision: str | None = "20260225_000002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_logs",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("email_type", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="sent"),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_email_logs_type_created", "email_logs", ["email_type", "created_at"])
    op.create_index("idx_email_logs_recipient_created", "email_logs", ["recipient", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_email_logs_recipient_created", table_name="email_logs")
    op.drop_index("idx_email_logs_type_created", table_name="email_logs")
    op.drop_table("email_logs")
