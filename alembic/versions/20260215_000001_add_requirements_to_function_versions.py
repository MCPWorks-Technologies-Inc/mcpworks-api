"""Add requirements column to function_versions

Allow functions to declare Python package dependencies from the
allow-listed package registry. Requirements are validated against
the registry at function creation time.

Revision ID: 20260215_000001
Revises: 20260210_000001
Create Date: 2026-02-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260215_000001"
down_revision: Union[str, None] = "20260210_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "function_versions",
        sa.Column(
            "requirements",
            sa.ARRAY(sa.String()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("function_versions", "requirements")
