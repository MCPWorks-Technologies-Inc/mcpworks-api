"""Value Ladder tier migration: rename founder tiers, add billing columns.

Drops and recreates CHECK constraints on users.tier, subscriptions.tier,
services.tier_required with new Value Ladder names (builder, pro).
Adds interval to subscriptions, tier_override columns to users.

Revision ID: 20260301_000003
Revises: 20260301_000002
Create Date: 2026-03-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260301_000003"
down_revision: str | None = "20260301_000002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VALID_TIERS = "('free', 'builder', 'pro', 'enterprise')"
OLD_TIERS = "('free', 'starter', 'pro', 'enterprise')"


def upgrade() -> None:
    # 1. Drop old CHECK constraints
    op.drop_constraint("chk_user_tier", "users", type_="check")
    op.drop_constraint("chk_subscription_tier", "subscriptions", type_="check")
    op.drop_constraint("chk_service_tier", "services", type_="check")

    # 2. Rename legacy tier values (safety net for any data)
    op.execute("UPDATE users SET tier = 'builder' WHERE tier IN ('founder', 'starter')")
    op.execute("UPDATE users SET tier = 'pro' WHERE tier = 'founder_pro'")
    op.execute("UPDATE subscriptions SET tier = 'builder' WHERE tier IN ('founder', 'starter')")
    op.execute("UPDATE subscriptions SET tier = 'pro' WHERE tier = 'founder_pro'")
    op.execute(
        "UPDATE services SET tier_required = 'builder' "
        "WHERE tier_required IN ('founder', 'starter')"
    )
    op.execute("UPDATE services SET tier_required = 'pro' WHERE tier_required = 'founder_pro'")

    # 3. Create new CHECK constraints with Value Ladder tier names
    op.create_check_constraint("chk_user_tier", "users", f"tier IN {VALID_TIERS}")
    op.create_check_constraint("chk_subscription_tier", "subscriptions", f"tier IN {VALID_TIERS}")
    op.create_check_constraint("chk_service_tier", "services", f"tier_required IN {VALID_TIERS}")

    # 4. Add interval column to subscriptions
    op.add_column(
        "subscriptions",
        sa.Column("interval", sa.String(10), server_default="monthly", nullable=True),
    )

    # 5. Add tier override columns to users
    op.add_column(
        "users",
        sa.Column("tier_override", sa.String(20), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("tier_override_reason", sa.String(255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "tier_override_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # 6. CHECK constraint on tier_override values
    op.create_check_constraint(
        "chk_user_tier_override",
        "users",
        f"tier_override IS NULL OR tier_override IN {VALID_TIERS}",
    )

    # 7. Enforce reason when override is set
    op.create_check_constraint(
        "chk_tier_override_reason",
        "users",
        "tier_override IS NULL OR tier_override_reason IS NOT NULL",
    )


def downgrade() -> None:
    # Remove override constraints
    op.drop_constraint("chk_tier_override_reason", "users", type_="check")
    op.drop_constraint("chk_user_tier_override", "users", type_="check")

    # Remove new columns
    op.drop_column("users", "tier_override_expires_at")
    op.drop_column("users", "tier_override_reason")
    op.drop_column("users", "tier_override")
    op.drop_column("subscriptions", "interval")

    # Revert CHECK constraints
    op.drop_constraint("chk_user_tier", "users", type_="check")
    op.drop_constraint("chk_subscription_tier", "subscriptions", type_="check")
    op.drop_constraint("chk_service_tier", "services", type_="check")

    # Revert tier values
    op.execute("UPDATE users SET tier = 'starter' WHERE tier = 'builder'")
    op.execute("UPDATE users SET tier = 'pro' WHERE tier = 'pro'")
    op.execute("UPDATE subscriptions SET tier = 'starter' WHERE tier = 'builder'")
    op.execute("UPDATE subscriptions SET tier = 'pro' WHERE tier = 'pro'")
    op.execute("UPDATE services SET tier_required = 'starter' WHERE tier_required = 'builder'")
    op.execute("UPDATE services SET tier_required = 'pro' WHERE tier_required = 'pro'")

    # Restore old constraints
    op.create_check_constraint("chk_user_tier", "users", f"tier IN {OLD_TIERS}")
    op.create_check_constraint("chk_subscription_tier", "subscriptions", f"tier IN {OLD_TIERS}")
    op.create_check_constraint("chk_service_tier", "services", f"tier_required IN {OLD_TIERS}")
