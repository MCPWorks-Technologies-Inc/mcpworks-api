"""Replace actor_ip (INET) with actor_ip_hash (String) for privacy.

ORDER-022: Never store raw IP addresses in security events.

Revision ID: 20260217_000002
Revises: 20260217_000001
Create Date: 2026-02-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260217_000002"
down_revision: Union[str, None] = "20260217_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("security_events", "actor_ip")
    op.add_column(
        "security_events",
        sa.Column("actor_ip_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("security_events", "actor_ip_hash")
    op.add_column(
        "security_events",
        sa.Column("actor_ip", sa.dialects.postgresql.INET(), nullable=True),
    )
