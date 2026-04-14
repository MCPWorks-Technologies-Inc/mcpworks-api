"""Add orchestration observability: extend agent_runs/agent_tool_calls, create schedule_fires.

Revision ID: 20260414_000001
Revises: 20260413_000001
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260414_000001"
down_revision = "20260413_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("outcome", sa.String(20), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("orchestration_mode", sa.String(20), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("limits_consumed", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("limits_configured", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_schedules.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("functions_called_count", sa.Integer(), nullable=True),
    )
    op.create_index("ix_agent_runs_outcome", "agent_runs", ["outcome"])
    op.create_index("ix_agent_runs_schedule", "agent_runs", ["schedule_id"])

    op.add_column(
        "agent_tool_calls",
        sa.Column(
            "decision_type",
            sa.String(20),
            nullable=False,
            server_default="call",
        ),
    )
    op.add_column(
        "agent_tool_calls",
        sa.Column("reason_category", sa.String(50), nullable=True),
    )

    op.create_table(
        "schedule_fires",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_detail", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["schedule_id"],
            ["agent_schedules.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schedule_fires_schedule_fired",
        "schedule_fires",
        ["schedule_id", "fired_at"],
    )
    op.create_index(
        "ix_schedule_fires_agent_fired",
        "schedule_fires",
        ["agent_id", "fired_at"],
    )
    op.create_index(
        "ix_schedule_fires_created",
        "schedule_fires",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_table("schedule_fires")
    op.drop_column("agent_tool_calls", "reason_category")
    op.drop_column("agent_tool_calls", "decision_type")
    op.drop_index("ix_agent_runs_schedule", table_name="agent_runs")
    op.drop_index("ix_agent_runs_outcome", table_name="agent_runs")
    op.drop_column("agent_runs", "functions_called_count")
    op.drop_column("agent_runs", "schedule_id")
    op.drop_column("agent_runs", "limits_configured")
    op.drop_column("agent_runs", "limits_consumed")
    op.drop_column("agent_runs", "orchestration_mode")
    op.drop_column("agent_runs", "outcome")
