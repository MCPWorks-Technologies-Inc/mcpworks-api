"""Add procedures framework: procedures, versions, executions tables.

Revision ID: 20260329_000001
Revises: 20260327_000001
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260329_000001"
down_revision = "20260327_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procedures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("namespace_id", UUID(as_uuid=True), sa.ForeignKey("namespaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", UUID(as_uuid=True), sa.ForeignKey("namespace_services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_procedures_namespace_id", "procedures", ["namespace_id"])
    op.create_index("ix_procedures_service_id", "procedures", ["service_id"])
    op.create_index(
        "uq_procedure_service_name",
        "procedures",
        ["service_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "procedure_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("procedure_id", UUID(as_uuid=True), sa.ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("steps", JSONB(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_procedure_versions_procedure_id", "procedure_versions", ["procedure_id"])
    op.create_unique_constraint("uq_procedure_version", "procedure_versions", ["procedure_id", "version"])

    op.create_table(
        "procedure_executions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("procedure_id", UUID(as_uuid=True), sa.ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("procedure_version", sa.Integer(), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("step_results", JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("input_context", JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_procedure_executions_procedure_id", "procedure_executions", ["procedure_id"])
    op.create_index("ix_procedure_executions_agent_id", "procedure_executions", ["agent_id"])
    op.create_index("ix_procedure_executions_status", "procedure_executions", ["procedure_id", "status"])

    op.add_column("agent_schedules", sa.Column("procedure_name", sa.String(255), nullable=True))
    op.add_column("agent_webhooks", sa.Column("procedure_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_webhooks", "procedure_name")
    op.drop_column("agent_schedules", "procedure_name")
    op.drop_table("procedure_executions")
    op.drop_table("procedure_versions")
    op.drop_table("procedures")
