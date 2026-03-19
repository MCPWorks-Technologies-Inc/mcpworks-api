"""Add public_safe to functions.

Controls whether a function is callable from public chat endpoints
(scratchpad chat proxy). Default false — nothing is exposed unless
the agent owner explicitly marks it safe.

Revision ID: 20260319_000004
Revises: 20260319_000003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260319_000004"
down_revision: str | None = "20260319_000003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "functions",
        sa.Column("public_safe", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("functions", "public_safe")
