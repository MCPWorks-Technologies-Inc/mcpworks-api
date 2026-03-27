"""Pydantic schemas for agent endpoints."""

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

AGENT_NAME_REGEX = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


TOOL_TIERS = ("execute_only", "standard", "builder", "admin")


class CreateAgentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=63)
    display_name: str | None = Field(None, max_length=255)
    tool_tier: str = Field(
        "standard", description="Tool access tier: execute_only, standard, builder, admin"
    )

    @field_validator("tool_tier")
    @classmethod
    def validate_tool_tier(cls, v: str) -> str:
        if v not in TOOL_TIERS:
            raise ValueError(f"tool_tier must be one of: {', '.join(TOOL_TIERS)}")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.lower()
        if not AGENT_NAME_REGEX.match(v):
            raise ValueError(
                "Agent name must be 1-63 lowercase alphanumeric characters or hyphens, "
                "starting and ending with alphanumeric"
            )
        return v


class AgentReplicaResponse(BaseModel):
    id: uuid.UUID
    replica_name: str
    status: str
    last_heartbeat: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str | None = None
    namespace_id: uuid.UUID | None = None
    namespace_name: str | None = None
    status: str
    target_replicas: int = 1
    replicas: list[AgentReplicaResponse] = []
    tool_tier: str = "standard"
    ai_engine: str | None = None
    ai_model: str | None = None
    system_prompt: str | None = None
    memory_limit_mb: int
    cpu_limit: float
    enabled: bool
    cloned_from_id: uuid.UUID | None = None
    scratchpad_token: str | None = None
    scratchpad_size_bytes: int = 0
    scratchpad_updated_at: datetime | None = None
    scratchpad_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentListResponse(BaseModel):
    agents: list[AgentResponse]
    total: int
    slots_used: int
    slots_available: int


class AgentSlotsResponse(BaseModel):
    slots_used: int
    slots_total: int
    slots_available: int
    tier: str


class StartStopResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    message: str


class DestroyResponse(BaseModel):
    id: uuid.UUID
    name: str
    message: str


class AgentRunResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    trigger_type: str
    trigger_detail: str | None = None
    function_name: str | None = None
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    result_summary: str | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class AgentRunListResponse(BaseModel):
    runs: list[AgentRunResponse]
    total: int


class CreateScheduleRequest(BaseModel):
    function_name: str = Field(..., min_length=1, max_length=255)
    cron_expression: str = Field(..., min_length=9, max_length=255)
    timezone: str = Field("UTC", max_length=50)
    mode: str = Field(
        "single",
        description="single: exactly one replica executes. cluster: all replicas execute independently.",
    )
    failure_policy: dict[str, Any] = Field(...)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("single", "cluster"):
            raise ValueError("mode must be 'single' or 'cluster'")
        return v

    @field_validator("failure_policy")
    @classmethod
    def validate_failure_policy(cls, v: dict[str, Any]) -> dict[str, Any]:
        strategy = v.get("strategy")
        if strategy not in ("continue", "auto_disable", "backoff"):
            raise ValueError(
                "failure_policy.strategy must be 'continue', 'auto_disable', or 'backoff'"
            )
        if strategy == "auto_disable" and "max_failures" not in v:
            raise ValueError("auto_disable strategy requires max_failures")
        if strategy == "backoff" and "backoff_factor" not in v:
            raise ValueError("backoff strategy requires backoff_factor")
        return v


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    function_name: str
    cron_expression: str
    cron_description: str = ""
    timezone: str
    mode: str = "single"
    failure_policy: dict[str, Any]
    enabled: bool
    consecutive_failures: int
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def set_cron_description(self) -> "ScheduleResponse":
        if self.cron_expression and not self.cron_description:
            try:
                from cron_descriptor import get_description

                self.cron_description = get_description(self.cron_expression)
            except Exception:
                self.cron_description = self.cron_expression
        return self


class ScheduleListResponse(BaseModel):
    schedules: list[ScheduleResponse]
    total: int


class CreateWebhookRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=255)
    handler_function_name: str = Field(..., min_length=1, max_length=255)
    secret: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        v = v.strip("/")
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-/]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$", v):
            raise ValueError(
                "Path must be alphanumeric with hyphens/slashes, no leading/trailing slashes"
            )
        return v


class WebhookResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    path: str
    handler_function_name: str
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookListResponse(BaseModel):
    webhooks: list[WebhookResponse]
    total: int


class SetStateRequest(BaseModel):
    value: Any = Field(...)


class StateResponse(BaseModel):
    key: str
    value: Any
    size_bytes: int
    updated_at: datetime


class StateKeyListResponse(BaseModel):
    keys: list[str]
    total_size_bytes: int
    max_size_bytes: int


class ConfigureAIRequest(BaseModel):
    engine: str = Field(...)
    model: str = Field(..., max_length=100)
    api_key: str | None = Field(None)
    system_prompt: str | None = None

    @field_validator("engine")
    @classmethod
    def validate_engine(cls, v: str) -> str:
        from mcpworks_api.models.agent import AI_ENGINES

        if v not in AI_ENGINES:
            raise ValueError(f"engine must be one of: {', '.join(AI_ENGINES)}")
        return v


class AIResponse(BaseModel):
    engine: str
    model: str
    system_prompt: str | None = None
    configured: bool = True


class CreateChannelRequest(BaseModel):
    channel_type: str = Field(...)
    config: dict[str, Any] = Field(...)

    @field_validator("channel_type")
    @classmethod
    def validate_channel_type(cls, v: str) -> str:
        if v not in ("discord", "slack", "whatsapp", "email"):
            raise ValueError("channel_type must be 'discord', 'slack', 'whatsapp', or 'email'")
        return v


class ChannelResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    channel_type: str
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


MCP_SERVER_TYPES = ("sse", "streamable_http", "stdio")


class McpServerConfig(BaseModel):
    type: str = Field(...)
    url: str | None = None
    command: str | None = None
    args: list[str] | None = None
    headers: dict[str, str] | None = None
    env: dict[str, str] | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in MCP_SERVER_TYPES:
            raise ValueError(f"type must be one of: {', '.join(MCP_SERVER_TYPES)}")
        return v


class ConfigureMcpServersRequest(BaseModel):
    servers: dict[str, McpServerConfig] = Field(...)

    @field_validator("servers")
    @classmethod
    def validate_servers(cls, v: dict[str, McpServerConfig]) -> dict[str, McpServerConfig]:
        if len(v) > 10:
            raise ValueError("Maximum 10 MCP servers per agent")
        for name in v:
            if not re.match(r"^[a-z0-9][a-z0-9_-]{0,30}[a-z0-9]?$", name):
                raise ValueError(
                    f"Server name '{name}' must be lowercase alphanumeric with hyphens/underscores"
                )
        return v


class McpServersResponse(BaseModel):
    servers: dict[str, dict[str, Any]]
    count: int


class ConfigureOrchestrationLimitsRequest(BaseModel):
    max_iterations: int | None = Field(None, ge=1, le=200)
    max_ai_tokens: int | None = Field(None, ge=1000, le=10_000_000)
    max_execution_seconds: int | None = Field(None, ge=10, le=3600)
    max_functions_called: int | None = Field(None, ge=1, le=500)


class OrchestrationLimitsResponse(BaseModel):
    limits: dict[str, int]
    source: str = Field(description="'custom' if agent has overrides, 'tier_default' otherwise")


class CloneAgentRequest(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=63)

    @field_validator("new_name")
    @classmethod
    def validate_new_name(cls, v: str) -> str:
        v = v.lower()
        if not AGENT_NAME_REGEX.match(v):
            raise ValueError(
                "Agent name must be 1-63 lowercase alphanumeric characters or hyphens, "
                "starting and ending with alphanumeric"
            )
        return v
