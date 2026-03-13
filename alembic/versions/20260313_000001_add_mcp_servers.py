"""Add mcp_servers JSONB column to agents

Revision ID: 20260313_000001
Revises: 20260312_000001
Create Date: 2026-03-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260313_000001"
down_revision: str = "20260312_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("mcp_servers", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "mcp_servers")
