"""Add agent_tool_calls table and agent_run_id to executions.

Revision ID: 20260412_000001
Revises: 20260409_000001
Create Date: 2026-04-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260412_000001"
down_revision = "20260409_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("tool_input", postgresql.JSONB(), nullable=True),
        sa.Column("result_preview", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_tool_calls_run_seq",
        "agent_tool_calls",
        ["agent_run_id", "sequence_number"],
    )
    op.create_index(
        "ix_agent_tool_calls_created",
        "agent_tool_calls",
        ["created_at"],
    )

    op.add_column(
        "executions",
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_executions_agent_run_id",
        "executions",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_executions_agent_run_id",
        "executions",
        ["agent_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_executions_agent_run_id", table_name="executions")
    op.drop_constraint("fk_executions_agent_run_id", "executions", type_="foreignkey")
    op.drop_column("executions", "agent_run_id")
    op.drop_index("ix_agent_tool_calls_created", table_name="agent_tool_calls")
    op.drop_index("ix_agent_tool_calls_run_seq", table_name="agent_tool_calls")
    op.drop_table("agent_tool_calls")
