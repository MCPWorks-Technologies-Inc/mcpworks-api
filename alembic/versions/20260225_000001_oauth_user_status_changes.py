"""User model changes for OAuth: nullable password_hash, rejection_reason column

Revision ID: 20260225_000001
Revises: 20260219_000001
Create Date: 2026-02-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260225_000001"
down_revision: str | None = "20260219_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)
    op.add_column("users", sa.Column("rejection_reason", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "rejection_reason")
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
