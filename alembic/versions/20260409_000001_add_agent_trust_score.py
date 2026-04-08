"""Add trust_score and trust_score_updated_at to agents.

Revision ID: 20260409_000001
Revises: 20260408_000002
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "20260409_000001"
down_revision = "20260408_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("trust_score", sa.Integer(), nullable=False, server_default="500"),
    )
    op.add_column(
        "agents",
        sa.Column("trust_score_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_agents_trust_score",
        "agents",
        "trust_score >= 0 AND trust_score <= 1000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agents_trust_score", "agents", type_="check")
    op.drop_column("agents", "trust_score_updated_at")
    op.drop_column("agents", "trust_score")
