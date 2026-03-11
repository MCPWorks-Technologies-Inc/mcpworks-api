"""Extend user tier check constraints to include agent tiers

Revision ID: 20260311_000006
Revises: 20260311_000005
Create Date: 2026-03-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260311_000006"
down_revision: str = "20260311_000005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALL_TIERS = (
    "'free'",
    "'builder'",
    "'pro'",
    "'enterprise'",
    "'builder-agent'",
    "'pro-agent'",
    "'enterprise-agent'",
)
BASE_TIERS = ("'free'", "'builder'", "'pro'", "'enterprise'")

TIER_ARRAY = f"ARRAY[{', '.join(ALL_TIERS)}]"
BASE_TIER_ARRAY = f"ARRAY[{', '.join(BASE_TIERS)}]"


def upgrade() -> None:
    op.drop_constraint("chk_user_tier", "users", type_="check")
    op.execute(
        f"ALTER TABLE users ADD CONSTRAINT chk_user_tier CHECK (tier IN ({', '.join(ALL_TIERS)}))"
    )

    op.drop_constraint("chk_user_tier_override", "users", type_="check")
    op.execute(
        f"ALTER TABLE users ADD CONSTRAINT chk_user_tier_override "
        f"CHECK (tier_override IS NULL OR tier_override IN ({', '.join(ALL_TIERS)}))"
    )


def downgrade() -> None:
    op.drop_constraint("chk_user_tier", "users", type_="check")
    op.execute(
        f"ALTER TABLE users ADD CONSTRAINT chk_user_tier CHECK (tier IN ({', '.join(BASE_TIERS)}))"
    )

    op.drop_constraint("chk_user_tier_override", "users", type_="check")
    op.execute(
        f"ALTER TABLE users ADD CONSTRAINT chk_user_tier_override "
        f"CHECK (tier_override IS NULL OR tier_override IN ({', '.join(BASE_TIERS)}))"
    )
