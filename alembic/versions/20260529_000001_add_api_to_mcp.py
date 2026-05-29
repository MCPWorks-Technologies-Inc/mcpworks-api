"""Add API → MCP tables (feature 019).

Creates namespace_api_servers, api_endpoints, api_proxy_calls, and the
agents.api_server_names column.

Revision ID: 20260529_000001
Revises: 20260401_000001
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "20260529_000001"
down_revision = "20260401_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "namespace_api_servers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "namespace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("namespaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(63), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("spec_source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("openapi_url", sa.String(500), nullable=True),
        sa.Column("auth", JSONB, nullable=False, server_default="[]"),
        sa.Column("credentials_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("credentials_dek_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("default_headers_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("default_headers_dek_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("endpoint_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("namespace_id", "name", name="uq_namespace_api_server_name"),
    )
    op.create_index(
        "ix_namespace_api_servers_namespace_id", "namespace_api_servers", ["namespace_id"]
    )

    op.create_table(
        "api_endpoints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "api_server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("namespace_api_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation_id", sa.String(128), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("summary", sa.String(255), nullable=True),
        sa.Column("param_schema", JSONB, nullable=False, server_default="{}"),
        sa.Column("request_body_schema", JSONB, nullable=True),
        sa.Column("response_schema", JSONB, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("published", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("source", sa.String(10), nullable=False, server_default="imported"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("api_server_id", "operation_id", name="uq_api_endpoint_operation"),
    )
    op.create_index(
        "ix_api_endpoints_server_enabled", "api_endpoints", ["api_server_id", "enabled"]
    )
    op.create_index(
        "ix_api_endpoints_server_published", "api_endpoints", ["api_server_id", "published"]
    )

    op.create_table(
        "api_proxy_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "namespace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("namespaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("api_server", sa.String(63), nullable=False),
        sa.Column("operation_id", sa.String(128), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("response_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("truncated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("called_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_api_proxy_calls_ns_time", "api_proxy_calls", ["namespace_id", "called_at"])
    op.create_index("ix_api_proxy_calls_ns_server", "api_proxy_calls", ["namespace_id", "api_server"])

    op.add_column("agents", sa.Column("api_server_names", ARRAY(sa.String), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "api_server_names")
    op.drop_index("ix_api_proxy_calls_ns_server", table_name="api_proxy_calls")
    op.drop_index("ix_api_proxy_calls_ns_time", table_name="api_proxy_calls")
    op.drop_table("api_proxy_calls")
    op.drop_index("ix_api_endpoints_server_published", table_name="api_endpoints")
    op.drop_index("ix_api_endpoints_server_enabled", table_name="api_endpoints")
    op.drop_table("api_endpoints")
    op.drop_index("ix_namespace_api_servers_namespace_id", table_name="namespace_api_servers")
    op.drop_table("namespace_api_servers")
