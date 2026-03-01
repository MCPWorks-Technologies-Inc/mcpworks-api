"""Rename whitelist columns and constraints to allowlist

Aligns database schema with inclusive terminology policy.

Revision ID: 20260301_000001
Revises: 20260215_000001
Create Date: 2026-03-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260301_000001"
down_revision: str | None = "20260215_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text("ALTER TABLE namespaces RENAME COLUMN network_whitelist TO network_allowlist")
    )
    conn.execute(
        sa.text("ALTER TABLE namespaces RENAME COLUMN whitelist_updated_at TO allowlist_updated_at")
    )
    conn.execute(
        sa.text(
            "ALTER TABLE namespaces "
            "RENAME COLUMN whitelist_changes_today TO allowlist_changes_today"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE namespaces "
            "RENAME CONSTRAINT whitelist_changes_positive "
            "TO allowlist_changes_positive"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text("ALTER TABLE namespaces RENAME COLUMN network_allowlist TO network_whitelist")
    )
    conn.execute(
        sa.text("ALTER TABLE namespaces RENAME COLUMN allowlist_updated_at TO whitelist_updated_at")
    )
    conn.execute(
        sa.text(
            "ALTER TABLE namespaces "
            "RENAME COLUMN allowlist_changes_today TO whitelist_changes_today"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE namespaces "
            "RENAME CONSTRAINT allowlist_changes_positive "
            "TO whitelist_changes_positive"
        )
    )
