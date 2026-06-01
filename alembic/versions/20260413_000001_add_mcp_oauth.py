"""Add OAuth columns to namespace_mcp_servers.

Revision ID: 20260413_000001
Revises: 20260412_000001
Create Date: 2026-04-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260413_000001"
down_revision = "20260412_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "namespace_mcp_servers",
        sa.Column("auth_type", sa.String(20), nullable=False, server_default="bearer"),
    )
    op.add_column(
        "namespace_mcp_servers",
        sa.Column("oauth_config_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "namespace_mcp_servers",
        sa.Column("oauth_config_dek", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "namespace_mcp_servers",
        sa.Column("oauth_tokens_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "namespace_mcp_servers",
        sa.Column("oauth_tokens_dek", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "namespace_mcp_servers",
        sa.Column("oauth_tokens_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("namespace_mcp_servers", "oauth_tokens_expires_at")
    op.drop_column("namespace_mcp_servers", "oauth_tokens_dek")
    op.drop_column("namespace_mcp_servers", "oauth_tokens_encrypted")
    op.drop_column("namespace_mcp_servers", "oauth_config_dek")
    op.drop_column("namespace_mcp_servers", "oauth_config_encrypted")
    op.drop_column("namespace_mcp_servers", "auth_type")
