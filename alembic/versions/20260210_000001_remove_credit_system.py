"""Remove credit system tables (PROBLEM-001)

Replace credit-based billing with execution-based limits per PRICING.md.

Revision ID: 20260210_000001
Revises: 20260209_000001
Create Date: 2026-02-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260210_000001"
down_revision: Union[str, None] = "20260209_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove credit system - executions are now tracked via Redis/BillingMiddleware."""
    # 1. Drop FK constraint from executions table
    op.drop_constraint(
        "executions_hold_transaction_id_fkey",
        "executions",
        type_="foreignkey",
    )

    # 2. Drop hold_transaction_id column from executions
    op.drop_column("executions", "hold_transaction_id")

    # 3. Drop credit_transactions table (has FK to credits)
    op.drop_index("idx_credit_txn_type", table_name="credit_transactions")
    op.drop_index(
        "idx_credit_txn_status_holds",
        table_name="credit_transactions",
    )
    op.drop_index(
        "idx_credit_txn_related",
        table_name="credit_transactions",
    )
    op.drop_index("idx_credit_txn_user", table_name="credit_transactions")
    op.drop_table("credit_transactions")

    # 4. Drop credits table
    op.drop_index("idx_credits_user_id", table_name="credits")
    op.drop_table("credits")


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
