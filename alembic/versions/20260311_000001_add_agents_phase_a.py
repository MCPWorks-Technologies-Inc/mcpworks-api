"""Add agents phase A: agents table, agent_runs table, subscription tier extension, function locked columns

Revision ID: 20260311_000001
Revises: 20260305_000001
Create Date: 2026-03-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260311_000001"
down_revision: str = "20260305_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("namespace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(63), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("container_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="creating"),
        sa.Column("ai_engine", sa.String(50), nullable=True),
        sa.Column("ai_model", sa.String(100), nullable=True),
        sa.Column("ai_api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("ai_api_key_dek_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("memory_limit_mb", sa.Integer(), nullable=False, server_default="256"),
        sa.Column("cpu_limit", sa.Float(), nullable=False, server_default="0.25"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "cloned_from_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["namespace_id"], ["namespaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cloned_from_id"], ["agents.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("account_id", "name", name="uq_agent_account_name"),
    )
    op.create_index("ix_agents_account_id", "agents", ["account_id"])
    op.create_index("ix_agents_namespace_id", "agents", ["namespace_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("trigger_detail", sa.String(255), nullable=True),
        sa.Column("function_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_runs_agent_created", "agent_runs", ["agent_id", "created_at"])
    op.create_index("ix_agent_runs_created", "agent_runs", ["created_at"])

    op.add_column(
        "functions",
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "functions",
        sa.Column(
            "locked_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "functions",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_functions_locked_by_users",
        "functions",
        "users",
        ["locked_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_functions_locked_by_users", "functions", type_="foreignkey")
    op.drop_column("functions", "locked_at")
    op.drop_column("functions", "locked_by")
    op.drop_column("functions", "locked")
    op.drop_index("ix_agent_runs_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_created", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_agents_namespace_id", table_name="agents")
    op.drop_index("ix_agents_account_id", table_name="agents")
    op.drop_table("agents")
