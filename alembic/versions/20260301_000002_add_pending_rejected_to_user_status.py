"""Add pending_approval and rejected to user status constraint

The chk_user_status constraint only allowed active/suspended/deleted but
the application uses pending_approval and rejected for the approval flow.

Revision ID: 20260301_000002
Revises: 20260301_000001
Create Date: 2026-03-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260301_000002"
down_revision: str | None = "20260301_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("chk_user_status", "users", type_="check")
    op.create_check_constraint(
        "chk_user_status",
        "users",
        "status IN ('active', 'suspended', 'deleted', 'pending_approval', 'rejected')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_user_status", "users", type_="check")
    op.create_check_constraint(
        "chk_user_status",
        "users",
        "status IN ('active', 'suspended', 'deleted')",
    )
