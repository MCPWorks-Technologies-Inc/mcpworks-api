"""Add call_count to namespaces, namespace_services, and functions.

Track tool invocation counts per resource for usage visibility.

Revision ID: 20260217_000001
Revises: 20260216_000002
Create Date: 2026-02-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260217_000001"
down_revision: Union[str, None] = "20260216_000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("namespaces", sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("namespace_services", sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("functions", sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("functions", "call_count")
    op.drop_column("namespace_services", "call_count")
    op.drop_column("namespaces", "call_count")
