"""Add pending_verification to user status constraint

The email verification PIN flow uses pending_verification status but
the chk_user_status constraint didn't include it.

Revision ID: 20260305_000001
Revises: 20260304_000001
Create Date: 2026-03-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260305_000001"
down_revision: str | None = "20260304_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("chk_user_status", "users", type_="check")
    op.create_check_constraint(
        "chk_user_status",
        "users",
        "status IN ('active', 'suspended', 'deleted', 'pending_approval', 'rejected', 'pending_verification')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_user_status", "users", type_="check")
    op.create_check_constraint(
        "chk_user_status",
        "users",
        "status IN ('active', 'suspended', 'deleted', 'pending_approval', 'rejected')",
    )
