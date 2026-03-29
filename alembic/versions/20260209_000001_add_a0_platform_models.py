"""Add A0 platform models (namespaces, services, functions, security)

Revision ID: 20260209_000001
Revises: 20251217_000002
Create Date: 2026-02-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260209_000001"
down_revision: str | None = "20251217_000002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create A0 platform tables and extend existing models."""

    # Create accounts table
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_accounts_user_id", "accounts", ["user_id"])

    # Create namespaces table
    op.create_table(
        "namespaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(63), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("network_whitelist", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("whitelist_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "whitelist_changes_today",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'",
            name="namespace_name_format",
        ),
        sa.CheckConstraint(
            "whitelist_changes_today >= 0",
            name="whitelist_changes_positive",
        ),
    )
    op.create_index("ix_namespaces_account_id", "namespaces", ["account_id"])
    op.create_index("ix_namespaces_name", "namespaces", ["name"])

    # Create namespace_services table
    op.create_table(
        "namespace_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "namespace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("namespaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(63), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("namespace_id", "name", name="uq_namespace_service_name"),
        sa.CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$'",
            name="namespace_service_name_format",
        ),
    )
    op.create_index("ix_namespace_services_namespace_id", "namespace_services", ["namespace_id"])
    op.create_index("ix_namespace_services_name", "namespace_services", ["name"])

    # Create functions table
    op.create_table(
        "functions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("namespace_services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(63), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("active_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("service_id", "name", name="uq_function_service_name"),
        sa.CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$'",
            name="function_name_format",
        ),
        sa.CheckConstraint("active_version > 0", name="function_active_version_positive"),
    )
    op.create_index("ix_functions_service_id", "functions", ["service_id"])
    op.create_index("ix_functions_name", "functions", ["name"])
    op.create_index("ix_functions_tags", "functions", ["tags"], postgresql_using="gin")

    # Create function_versions table
    op.create_table(
        "function_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "function_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("functions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("backend", sa.String(50), nullable=False),
        sa.Column("code", sa.Text, nullable=True),
        sa.Column("config", postgresql.JSONB, nullable=True),
        sa.Column("input_schema", postgresql.JSONB, nullable=True),
        sa.Column("output_schema", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("function_id", "version", name="uq_function_version_number"),
        sa.CheckConstraint("version > 0", name="function_version_positive"),
        sa.CheckConstraint(
            "backend IN ('code_sandbox', 'nanobot', 'github_repo')",
            name="function_version_backend_valid",
        ),
    )
    op.create_index("ix_function_versions_function_id", "function_versions", ["function_id"])
    op.create_index(
        "ix_function_versions_version",
        "function_versions",
        ["function_id", "version"],
    )
    op.create_index("ix_function_versions_backend", "function_versions", ["backend"])

    # Create security_events table
    op.create_table(
        "security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_ip", postgresql.INET, nullable=True),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')",
            name="security_event_severity_valid",
        ),
    )
    op.create_index("ix_security_events_timestamp", "security_events", ["timestamp"])
    op.create_index("ix_security_events_event_type", "security_events", ["event_type"])
    op.create_index("ix_security_events_severity", "security_events", ["severity"])
    op.create_index("ix_security_events_actor_id", "security_events", ["actor_id"])
    op.create_index(
        "ix_security_events_timestamp_severity",
        "security_events",
        ["timestamp", "severity"],
    )

    # Create webhooks table
    op.create_table(
        "webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("secret_hash", sa.String(255), nullable=False),
        sa.Column("events", postgresql.ARRAY(sa.String), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("url ~ '^https://'", name="webhook_url_https"),
    )
    op.create_index("ix_webhooks_account_id", "webhooks", ["account_id"])
    op.create_index("ix_webhooks_enabled", "webhooks", ["enabled"])
    op.create_index("ix_webhooks_events", "webhooks", ["events"], postgresql_using="gin")

    # Extend api_keys table with namespace_id
    op.add_column(
        "api_keys",
        sa.Column(
            "namespace_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_api_keys_namespace_id",
        "api_keys",
        "namespaces",
        ["namespace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_api_keys_namespace", "api_keys", ["namespace_id"])

    # Extend executions table with A0 fields
    op.add_column(
        "executions",
        sa.Column("function_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "executions",
        sa.Column("function_version_num", sa.Integer, nullable=True),
    )
    op.add_column(
        "executions",
        sa.Column("backend", sa.String(50), nullable=True),
    )
    op.add_column(
        "executions",
        sa.Column("credit_cost", sa.Float, nullable=True),
    )
    op.add_column(
        "executions",
        sa.Column("backend_metadata", postgresql.JSONB, nullable=True),
    )
    op.create_foreign_key(
        "fk_executions_function_id",
        "executions",
        "functions",
        ["function_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_executions_function_id", "executions", ["function_id"])
    op.create_index("ix_executions_function_created", "executions", ["function_id", "created_at"])


def downgrade() -> None:
    """Remove A0 platform tables and revert existing model extensions."""

    # Drop executions extensions
    op.drop_index("ix_executions_function_created", table_name="executions")
    op.drop_index("ix_executions_function_id", table_name="executions")
    op.drop_constraint("fk_executions_function_id", "executions", type_="foreignkey")
    op.drop_column("executions", "backend_metadata")
    op.drop_column("executions", "credit_cost")
    op.drop_column("executions", "backend")
    op.drop_column("executions", "function_version_num")
    op.drop_column("executions", "function_id")

    # Drop api_keys extensions
    op.drop_index("idx_api_keys_namespace", table_name="api_keys")
    op.drop_constraint("fk_api_keys_namespace_id", "api_keys", type_="foreignkey")
    op.drop_column("api_keys", "namespace_id")

    # Drop webhooks table
    op.drop_index("ix_webhooks_events", table_name="webhooks")
    op.drop_index("ix_webhooks_enabled", table_name="webhooks")
    op.drop_index("ix_webhooks_account_id", table_name="webhooks")
    op.drop_table("webhooks")

    # Drop security_events table
    op.drop_index("ix_security_events_timestamp_severity", table_name="security_events")
    op.drop_index("ix_security_events_actor_id", table_name="security_events")
    op.drop_index("ix_security_events_severity", table_name="security_events")
    op.drop_index("ix_security_events_event_type", table_name="security_events")
    op.drop_index("ix_security_events_timestamp", table_name="security_events")
    op.drop_table("security_events")

    # Drop function_versions table
    op.drop_index("ix_function_versions_backend", table_name="function_versions")
    op.drop_index("ix_function_versions_version", table_name="function_versions")
    op.drop_index("ix_function_versions_function_id", table_name="function_versions")
    op.drop_table("function_versions")

    # Drop functions table
    op.drop_index("ix_functions_tags", table_name="functions")
    op.drop_index("ix_functions_name", table_name="functions")
    op.drop_index("ix_functions_service_id", table_name="functions")
    op.drop_table("functions")

    # Drop namespace_services table
    op.drop_index("ix_namespace_services_name", table_name="namespace_services")
    op.drop_index("ix_namespace_services_namespace_id", table_name="namespace_services")
    op.drop_table("namespace_services")

    # Drop namespaces table
    op.drop_index("ix_namespaces_name", table_name="namespaces")
    op.drop_index("ix_namespaces_account_id", table_name="namespaces")
    op.drop_table("namespaces")

    # Drop accounts table
    op.drop_index("idx_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
