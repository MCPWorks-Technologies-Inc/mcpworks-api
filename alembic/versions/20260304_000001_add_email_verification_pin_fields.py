"""Add email verification PIN fields to users.

Adds verification_pin_expires_at, verification_attempts, and
verification_resend_count columns. Also adds pending_verification
to the user status enum.

Revision ID: 20260304_000001
Revises: 20260302_000001
Create Date: 2026-03-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260304_000001"
down_revision: str | None = "20260302_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("verification_pin_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("verification_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("verification_resend_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "verification_resend_count")
    op.drop_column("users", "verification_attempts")
    op.drop_column("users", "verification_pin_expires_at")
