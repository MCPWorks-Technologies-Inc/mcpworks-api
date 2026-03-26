"""Add mcp_proxy_calls and mcp_execution_stats tables.

Revision ID: 20260326_000004
Revises: 20260326_000003
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260326_000004"
down_revision = "20260326_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_proxy_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "namespace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("namespaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("server_name", sa.String(63), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column(
            "called_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("response_bytes", sa.Integer, nullable=False),
        sa.Column("response_tokens_est", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("truncated", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("injections_found", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_mcp_proxy_calls_ns_time", "mcp_proxy_calls", ["namespace_id", "called_at"]
    )
    op.create_index(
        "ix_mcp_proxy_calls_ns_server_tool_time",
        "mcp_proxy_calls",
        ["namespace_id", "server_name", "tool_name", "called_at"],
    )

    op.create_table(
        "mcp_execution_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "namespace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("namespaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("execution_id", sa.String(64), nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("mcp_calls_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mcp_bytes_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("result_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_saved_est", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_mcp_execution_stats_ns_time",
        "mcp_execution_stats",
        ["namespace_id", "executed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_execution_stats_ns_time", table_name="mcp_execution_stats")
    op.drop_table("mcp_execution_stats")
    op.drop_index("ix_mcp_proxy_calls_ns_server_tool_time", table_name="mcp_proxy_calls")
    op.drop_index("ix_mcp_proxy_calls_ns_time", table_name="mcp_proxy_calls")
    op.drop_table("mcp_proxy_calls")
