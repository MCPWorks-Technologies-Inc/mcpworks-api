"""Initial schema - create all tables

Revision ID: 20251217_000001
Revises:
Create Date: 2025-12-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20251217_000001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables for initial schema."""
    # Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "tier",
            sa.String(20),
            nullable=False,
            server_default="free",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("verification_token", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "tier IN ('free', 'starter', 'pro', 'enterprise')",
            name="chk_user_tier",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="chk_user_status",
        ),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_status", "users", ["status"])

    # API Keys table
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_api_keys_user", "api_keys", ["user_id"])
    op.create_index("idx_api_keys_hash", "api_keys", ["key_hash"])
    op.create_index("idx_api_keys_prefix", "api_keys", ["key_prefix"])

    # Credits table
    op.create_table(
        "credits",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "available_balance",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "held_balance",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "lifetime_earned",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "lifetime_spent",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("available_balance >= 0", name="chk_available_non_negative"),
        sa.CheckConstraint("held_balance >= 0", name="chk_held_non_negative"),
    )

    # Credit Transactions table
    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("balance_before", sa.Numeric(10, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "hold_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_transactions.id"),
            nullable=True,
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transaction_data", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "type IN ('hold', 'commit', 'release', 'purchase', 'grant', 'refund')",
            name="chk_transaction_type",
        ),
    )
    op.create_index("idx_credit_txn_user", "credit_transactions", ["user_id"])
    op.create_index(
        "idx_credit_txn_hold",
        "credit_transactions",
        ["hold_id"],
        postgresql_where="hold_id IS NOT NULL",
    )
    op.create_index(
        "idx_credit_txn_created",
        "credit_transactions",
        [sa.text("created_at DESC")],
    )
    op.create_index("idx_credit_txn_type", "credit_transactions", ["type"])

    # Subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(255), unique=True, nullable=True),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "tier IN ('free', 'starter', 'pro', 'enterprise')",
            name="chk_subscription_tier",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'cancelled', 'past_due', 'trialing')",
            name="chk_subscription_status",
        ),
    )
    op.create_index("idx_subscriptions_user", "subscriptions", ["user_id"])
    op.create_index("idx_subscriptions_stripe", "subscriptions", ["stripe_subscription_id"])

    # Services table
    op.create_table(
        "services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(255), nullable=False),
        sa.Column("health_check_url", sa.String(255), nullable=True),
        sa.Column("credit_cost", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("tier_required", sa.String(20), nullable=False, server_default="free"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "tier_required IN ('free', 'starter', 'pro', 'enterprise')",
            name="chk_service_tier",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'degraded')",
            name="chk_service_status",
        ),
    )
    op.create_index("idx_services_name", "services", ["name"])
    op.create_index("idx_services_status", "services", ["status"])

    # Audit Logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("event_data", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_audit_user", "audit_logs", ["user_id"])
    op.create_index("idx_audit_action", "audit_logs", ["action"])
    op.create_index("idx_audit_created", "audit_logs", [sa.text("created_at DESC")])
    op.create_index("idx_audit_resource", "audit_logs", ["resource_type", "resource_id"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("audit_logs")
    op.drop_table("services")
    op.drop_table("subscriptions")
    op.drop_table("credit_transactions")
    op.drop_table("credits")
    op.drop_table("api_keys")
    op.drop_table("users")
