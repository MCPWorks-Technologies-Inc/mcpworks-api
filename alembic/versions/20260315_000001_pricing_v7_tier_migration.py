"""Pricing v7.0.0: Remove free/builder tiers, add trial/dedicated.

Migrate existing users on removed tiers to pro-agent per board decision 2026-03-12.
All accounts get agent functionality — no non-agent tiers for users.
- free -> pro-agent
- builder -> pro-agent
- pro -> pro-agent
- builder-agent -> pro-agent
- enterprise -> enterprise-agent

Revision ID: 20260315_000001
Revises: 20260314_000001
"""

from alembic import op

revision: str = "20260315_000001"
down_revision: str | None = "20260314_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET tier = 'pro-agent' WHERE tier IN ('free', 'builder', 'pro', 'builder-agent')"
    )
    op.execute("UPDATE users SET tier = 'enterprise-agent' WHERE tier = 'enterprise'")

    op.execute(
        "UPDATE users SET tier_override = 'pro-agent' "
        "WHERE tier_override IN ('free', 'builder', 'pro', 'builder-agent')"
    )
    op.execute(
        "UPDATE users SET tier_override = 'enterprise-agent' WHERE tier_override = 'enterprise'"
    )

    op.execute(
        "UPDATE subscriptions SET tier = 'pro-agent' "
        "WHERE tier IN ('free', 'builder', 'pro', 'builder-agent')"
    )
    op.execute("UPDATE subscriptions SET tier = 'enterprise-agent' WHERE tier = 'enterprise'")

    op.execute("UPDATE namespace_services SET tier_required = 'trial' WHERE tier_required = 'free'")
    op.execute(
        "UPDATE namespace_services SET tier_required = 'pro' WHERE tier_required = 'builder'"
    )


def downgrade() -> None:
    pass
