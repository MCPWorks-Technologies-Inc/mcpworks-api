"""Remove credit system tables (PROBLEM-001)

Replace credit-based billing with execution-based limits per PRICING.md.

Revision ID: 20260210_000001
Revises: 20260209_000001
Create Date: 2026-02-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260210_000001"
down_revision: str | None = "20260209_000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove credit system - executions are now tracked via Redis/BillingMiddleware.

    Uses IF EXISTS to be idempotent (credit tables may not exist in all environments).
    """
    conn = op.get_bind()

    # 1. Drop FK constraint from executions table (if exists)
    conn.execute(
        sa.text("""
        ALTER TABLE executions
        DROP CONSTRAINT IF EXISTS executions_hold_transaction_id_fkey
    """)
    )

    # 2. Drop hold_transaction_id column from executions (if exists)
    conn.execute(
        sa.text("""
        ALTER TABLE executions
        DROP COLUMN IF EXISTS hold_transaction_id
    """)
    )

    # 3. Drop credit_transactions indexes and table (if exist)
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_credit_txn_type"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_credit_txn_status_holds"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_credit_txn_related"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_credit_txn_user"))
    conn.execute(sa.text("DROP TABLE IF EXISTS credit_transactions CASCADE"))

    # 4. Drop credits table (if exists)
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_credits_user_id"))
    conn.execute(sa.text("DROP TABLE IF EXISTS credits CASCADE"))


def downgrade() -> None:
    """Recreate credit system tables."""
    # 1. Recreate credits table
    op.create_table(
        "credits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "available_balance",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "held_balance",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
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
            "available_balance >= 0",
            name="chk_available_balance_positive",
        ),
        sa.CheckConstraint(
            "held_balance >= 0",
            name="chk_held_balance_positive",
        ),
    )
    op.create_index("idx_credits_user_id", "credits", ["user_id"])

    # 2. Recreate credit_transactions table
    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "type",
            sa.String(20),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(12, 2),
            nullable=False,
        ),
        sa.Column(
            "related_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_transactions.id"),
            nullable=True,
        ),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="completed",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "type IN ('hold', 'commit', 'release', 'grant', 'expire')",
            name="chk_transaction_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'expired')",
            name="chk_transaction_status",
        ),
    )
    op.create_index("idx_credit_txn_user", "credit_transactions", ["user_id"])
    op.create_index(
        "idx_credit_txn_related",
        "credit_transactions",
        ["related_transaction_id"],
    )
    op.create_index(
        "idx_credit_txn_status_holds",
        "credit_transactions",
        ["status", "expires_at"],
    )
    op.create_index("idx_credit_txn_type", "credit_transactions", ["type"])

    # 3. Add hold_transaction_id column back to executions
    op.add_column(
        "executions",
        sa.Column(
            "hold_transaction_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    # 4. Recreate FK constraint
    op.create_foreign_key(
        "executions_hold_transaction_id_fkey",
        "executions",
        "credit_transactions",
        ["hold_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )
