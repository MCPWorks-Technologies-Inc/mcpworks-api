"""Add orchestration_limits JSONB column to agents.

Per-agent overrides for orchestration limits (max_iterations, max_ai_tokens,
max_execution_seconds, max_functions_called). NULL means use tier defaults.

Revision ID: 20260315_000002
Revises: 20260315_000001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260315_000002"
down_revision: str | None = "20260315_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("orchestration_limits", sa.dialects.postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "orchestration_limits")
