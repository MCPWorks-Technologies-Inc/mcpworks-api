"""Create namespace_shares table for namespace sharing.

Revision ID: 20260228_000002
Revises: 20260228_000001
Create Date: 2026-02-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260228_000002"
down_revision: str | None = "20260228_000001"
branch_labels: tuple | None = None
depends_on: tuple | None = None


def upgrade() -> None:
    op.create_table(
        "namespace_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "namespace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("namespaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "granted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "permissions",
            postgresql.ARRAY(sa.Text),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("namespace_id", "user_id", name="uq_namespace_share_user"),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'revoked')",
            name="ck_namespace_share_status",
        ),
    )
    op.create_index("ix_namespace_shares_namespace_id", "namespace_shares", ["namespace_id"])
    op.create_index("ix_namespace_shares_user_id", "namespace_shares", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_namespace_shares_user_id", table_name="namespace_shares")
    op.drop_index("ix_namespace_shares_namespace_id", table_name="namespace_shares")
    op.drop_table("namespace_shares")
