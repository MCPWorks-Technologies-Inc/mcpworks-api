"""Add namespace_mcp_servers table and mcp_server_names to agents.

Revision ID: 20260326_000002
Revises: 20260326_000001
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260326_000002"
down_revision = "20260326_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "namespace_mcp_servers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "namespace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("namespaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(63), nullable=False),
        sa.Column(
            "transport", sa.String(20), nullable=False, server_default="streamable_http"
        ),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("command", sa.String(500), nullable=True),
        sa.Column("command_args", postgresql.JSONB, nullable=True),
        sa.Column("headers_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("headers_dek_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("settings", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("env_vars", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "tool_schemas", postgresql.JSONB, nullable=False, server_default="[]"
        ),
        sa.Column("tool_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "namespace_id", "name", name="uq_namespace_mcp_server_name"
        ),
    )
    op.create_index(
        "ix_namespace_mcp_servers_namespace_id",
        "namespace_mcp_servers",
        ["namespace_id"],
    )

    op.add_column(
        "agents",
        sa.Column(
            "mcp_server_names",
            postgresql.ARRAY(sa.String),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "mcp_server_names")
    op.drop_index(
        "ix_namespace_mcp_servers_namespace_id", table_name="namespace_mcp_servers"
    )
    op.drop_table("namespace_mcp_servers")
