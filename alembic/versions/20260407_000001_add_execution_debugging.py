"""Add execution debugging columns and indexes to executions table.

Revision ID: 20260407_000001
Revises: 20260401_000001
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260407_000001"
down_revision = "20260401_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("executions", sa.Column("namespace_id", UUID(as_uuid=True), nullable=True))
    op.add_column("executions", sa.Column("service_name", sa.String(255), nullable=True))
    op.add_column("executions", sa.Column("function_name", sa.String(255), nullable=True))
    op.add_column("executions", sa.Column("execution_time_ms", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_executions_namespace_id",
        "executions",
        "namespaces",
        ["namespace_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index("ix_executions_namespace_id", "executions", ["namespace_id"])
    op.create_index("ix_executions_ns_function", "executions", ["namespace_id", "service_name", "function_name"])
    op.create_index("ix_executions_ns_status", "executions", ["namespace_id", "status"])
    op.create_index("ix_executions_ns_created", "executions", ["namespace_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_executions_ns_created", table_name="executions")
    op.drop_index("ix_executions_ns_status", table_name="executions")
    op.drop_index("ix_executions_ns_function", table_name="executions")
    op.drop_index("ix_executions_namespace_id", table_name="executions")
    op.drop_constraint("fk_executions_namespace_id", "executions", type_="foreignkey")
    op.drop_column("executions", "execution_time_ms")
    op.drop_column("executions", "function_name")
    op.drop_column("executions", "service_name")
    op.drop_column("executions", "namespace_id")
