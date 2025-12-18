"""Add executions table for workflow execution tracking

Revision ID: 20251217_000002
Revises: 20251217_000001
Create Date: 2025-12-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20251217_000002"
down_revision: Union[str, None] = "20251217_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create executions table."""
    op.create_table(
        "executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workflow_id", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "hold_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("input_data", postgresql.JSONB, nullable=True),
        sa.Column("result_data", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'timed_out')",
            name="chk_execution_status",
        ),
    )
    op.create_index("idx_executions_user_id", "executions", ["user_id"])
    op.create_index("idx_executions_workflow_id", "executions", ["workflow_id"])
    op.create_index("idx_executions_status", "executions", ["status"])


def downgrade() -> None:
    """Drop executions table."""
    op.drop_index("idx_executions_status", table_name="executions")
    op.drop_index("idx_executions_workflow_id", table_name="executions")
    op.drop_index("idx_executions_user_id", table_name="executions")
    op.drop_table("executions")
