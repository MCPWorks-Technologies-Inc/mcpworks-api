"""Add agent clusters: replicas table, scheduled jobs, target_replicas, schedule mode.

Revision ID: 20260327_000001
Revises: 20260326_000004
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260327_000001"
down_revision = "20260326_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("target_replicas", sa.Integer(), nullable=False, server_default="1"))

    op.add_column("agent_schedules", sa.Column("mode", sa.String(10), nullable=False, server_default="single"))

    op.create_table(
        "agent_replicas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("replica_name", sa.String(63), nullable=False),
        sa.Column("container_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="creating"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_replicas_agent_id", "agent_replicas", ["agent_id"])
    op.create_index("ix_agent_replicas_status", "agent_replicas", ["agent_id", "status"])
    op.create_unique_constraint("uq_agent_replica_name", "agent_replicas", ["agent_id", "replica_name"])

    op.create_table(
        "scheduled_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_id", UUID(as_uuid=True), sa.ForeignKey("agent_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("replica_id", UUID(as_uuid=True), sa.ForeignKey("agent_replicas.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fire_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("claimed_by", UUID(as_uuid=True), sa.ForeignKey("agent_replicas.id", ondelete="SET NULL"), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_scheduled_jobs_pending",
        "scheduled_jobs",
        ["agent_id", "status"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_scheduled_jobs_schedule", "scheduled_jobs", ["schedule_id", "fire_time"])
    op.create_index("ix_scheduled_jobs_cleanup", "scheduled_jobs", ["status", "completed_at"])

    op.execute("""
        INSERT INTO agent_replicas (id, agent_id, replica_name, container_id, status, created_at)
        SELECT gen_random_uuid(), id, 'prime-falcon', container_id,
               CASE WHEN status IN ('creating', 'running', 'stopped', 'error') THEN status ELSE 'stopped' END,
               created_at
        FROM agents
        WHERE container_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_table("scheduled_jobs")
    op.drop_table("agent_replicas")
    op.drop_column("agent_schedules", "mode")
    op.drop_column("agents", "target_replicas")
