"""Agent models for containerized autonomous agents."""

import re
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

AGENT_NAME_REGEX = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

AGENT_STATUSES = ("creating", "running", "stopped", "error", "destroying")
RUN_STATUSES = ("running", "completed", "failed", "timeout")
TRIGGER_TYPES = ("cron", "webhook", "manual", "ai", "heartbeat")
CHANNEL_TYPES = ("discord", "slack", "whatsapp", "email")
ORCHESTRATION_MODES = ("direct", "reason_first", "run_then_reason")
AI_ENGINES = (
    "anthropic",
    "openai",
    "google",
    "openrouter",
    "grok",
    "deepseek",
    "kimi",
    "ollama",
)


class Agent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agents"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(63), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    container_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="creating")

    ai_engine: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ai_api_key_dek_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    memory_limit_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=256)
    cpu_limit: Mapped[float] = mapped_column(Float, nullable=False, default=0.25)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tool_tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default="standard", server_default="standard"
    )
    scheduled_tool_tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default="execute_only", server_default="execute_only"
    )
    auto_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mcp_servers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # DEPRECATED — use mcp_server_names
    mcp_server_names: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    orchestration_limits: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    heartbeat_interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heartbeat_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    heartbeat_next_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cloned_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    scratchpad_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chat_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scratchpad_size_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    scratchpad_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scratchpad_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    runs: Mapped[list["AgentRun"]] = relationship(
        "AgentRun",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="desc(AgentRun.created_at)",
    )
    schedules: Mapped[list["AgentSchedule"]] = relationship(
        "AgentSchedule",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    webhooks: Mapped[list["AgentWebhook"]] = relationship(
        "AgentWebhook",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    state_entries: Mapped[list["AgentState"]] = relationship(
        "AgentState",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    channels: Mapped[list["AgentChannel"]] = relationship(
        "AgentChannel",
        back_populates="agent",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_agent_account_name"),
        Index("ix_agents_account_id", "account_id"),
        Index("ix_agents_namespace_id", "namespace_id"),
        Index(
            "ix_agents_scratchpad_token",
            "scratchpad_token",
            unique=True,
            postgresql_where=text("scratchpad_token IS NOT NULL"),
        ),
        Index(
            "ix_agents_chat_token",
            "chat_token",
            unique=True,
            postgresql_where=text("chat_token IS NOT NULL"),
        ),
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        if not value or not AGENT_NAME_REGEX.match(value):
            raise ValueError(
                "Agent name must be 1-63 lowercase alphanumeric characters or hyphens, "
                "starting and ending with alphanumeric"
            )
        return value

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        if value not in AGENT_STATUSES:
            raise ValueError(f"Invalid agent status: {value}")
        return value

    @validates("auto_channel")
    def validate_auto_channel(self, key: str, value: str | None) -> str | None:
        if value is not None and value not in CHANNEL_TYPES:
            raise ValueError(f"Invalid auto_channel type: {value}")
        return value


class AgentRun(Base, UUIDMixin):
    __tablename__ = "agent_runs"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    function_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="runs")

    __table_args__ = (
        Index("ix_agent_runs_agent_created", "agent_id", "created_at"),
        Index("ix_agent_runs_created", "created_at"),
    )

    @validates("trigger_type")
    def validate_trigger_type(self, key: str, value: str) -> str:
        if value not in TRIGGER_TYPES:
            raise ValueError(f"Invalid trigger type: {value}")
        return value

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        if value not in RUN_STATUSES:
            raise ValueError(f"Invalid run status: {value}")
        return value


class AgentSchedule(Base, UUIDMixin):
    __tablename__ = "agent_schedules"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    function_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    failure_policy: Mapped[dict] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    orchestration_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="direct")
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="schedules")

    __table_args__ = (Index("ix_agent_schedules_agent_id", "agent_id"),)

    @validates("orchestration_mode")
    def validate_orchestration_mode(self, key: str, value: str) -> str:
        if value not in ORCHESTRATION_MODES:
            raise ValueError(f"Invalid orchestration mode: {value}")
        return value


class AgentWebhook(Base, UUIDMixin):
    __tablename__ = "agent_webhooks"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    handler_function_name: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    orchestration_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="direct")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="webhooks")

    __table_args__ = (
        UniqueConstraint("agent_id", "path", name="uq_agent_webhook_path"),
        Index("ix_agent_webhooks_agent_id", "agent_id"),
    )

    @validates("orchestration_mode")
    def validate_orchestration_mode(self, key: str, value: str) -> str:
        if value not in ORCHESTRATION_MODES:
            raise ValueError(f"Invalid orchestration mode: {value}")
        return value


class AgentState(Base, UUIDMixin):
    __tablename__ = "agent_state"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    value_dek_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="state_entries")

    __table_args__ = (
        UniqueConstraint("agent_id", "key", name="uq_agent_state_key"),
        Index("ix_agent_state_agent_id", "agent_id"),
    )


class AgentChannel(Base, UUIDMixin):
    __tablename__ = "agent_channels"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    config_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    config_dek_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="channels")

    __table_args__ = (
        UniqueConstraint("agent_id", "channel_type", name="uq_agent_channel_type"),
        Index("ix_agent_channels_agent_id", "agent_id"),
    )

    @validates("channel_type")
    def validate_channel_type(self, key: str, value: str) -> str:
        if value not in CHANNEL_TYPES:
            raise ValueError(f"Invalid channel type: {value}")
        return value
