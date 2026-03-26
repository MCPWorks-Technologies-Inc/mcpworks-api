"""Pydantic schemas for MCP server management operations."""

from pydantic import BaseModel, Field


class AddServerResponse(BaseModel):
    status: str = "added"
    name: str
    url: str | None = None
    transport: str
    tool_count: int
    tools: list[str] = Field(default_factory=list)


class RemoveServerResponse(BaseModel):
    status: str = "removed"
    name: str


class ServerSummary(BaseModel):
    name: str
    url: str | None = None
    transport: str
    tool_count: int
    enabled: bool
    last_connected: str | None = None


class ListServersResponse(BaseModel):
    servers: list[ServerSummary] = Field(default_factory=list)


class ToolSummary(BaseModel):
    name: str
    description: str = ""


class DescribeServerResponse(BaseModel):
    name: str
    url: str | None = None
    transport: str
    enabled: bool
    settings: dict = Field(default_factory=dict)
    env_vars: dict = Field(default_factory=dict)
    tool_count: int
    tools: list[ToolSummary] = Field(default_factory=list)
    last_connected: str | None = None


class RefreshResponse(BaseModel):
    status: str = "refreshed"
    name: str
    tool_count: int
    tools_added: list[str] = Field(default_factory=list)
    tools_removed: list[str] = Field(default_factory=list)


class UpdateServerResponse(BaseModel):
    status: str = "updated"
    name: str


class SettingsResponse(BaseModel):
    name: str
    settings: dict


class EnvVarsResponse(BaseModel):
    name: str
    env_vars: dict


class ConfigureAgentMcpResponse(BaseModel):
    agent: str
    mcp_servers: list[str] = Field(default_factory=list)


class ProxyRequest(BaseModel):
    server: str
    tool: str
    arguments: dict = Field(default_factory=dict)


class ProxyResponse(BaseModel):
    result: str | dict | list | None = None
    truncated: bool = False
    error: str | None = None
    error_type: str | None = None
