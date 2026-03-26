"""Add namespace_git_remotes table.

Revision ID: 20260326_000001
Revises: 20260319_000004_add_public_safe_to_functions
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260326_000001"
down_revision = "20260319_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "namespace_git_remotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "namespace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("namespaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("git_url", sa.String(500), nullable=False),
        sa.Column("git_branch", sa.String(100), nullable=False, server_default="main"),
        sa.Column("token_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("token_dek_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("last_export_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_export_sha", sa.String(40), nullable=True),
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
        sa.UniqueConstraint("namespace_id", name="uq_namespace_git_remote_namespace"),
    )
    op.create_index(
        "ix_namespace_git_remotes_id", "namespace_git_remotes", ["id"]
    )


def downgrade() -> None:
    op.drop_index("ix_namespace_git_remotes_id", table_name="namespace_git_remotes")
    op.drop_table("namespace_git_remotes")
