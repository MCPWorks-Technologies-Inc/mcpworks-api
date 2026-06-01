"""Pydantic response schemas for .well-known/mcp.json server cards."""

from pydantic import BaseModel, Field


class TransportInfo(BaseModel):
    type: str = "https+sse"


class EndpointsInfo(BaseModel):
    create: str
    run: str


class ToolSummary(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict | None = None


class NamespaceServerCard(BaseModel):
    schema_version: str = "0.1.0"
    name: str
    description: str | None = None
    protocol_version: str = "2024-11-05"
    transports: list[TransportInfo] = Field(default_factory=lambda: [TransportInfo()])
    endpoints: EndpointsInfo
    tools: list[ToolSummary] = Field(default_factory=list)
    private_tool_count: int = 0
    service_count: int = 0
    total_tool_count: int = 0


class NamespaceEntry(BaseModel):
    name: str
    description: str | None = None
    server_card_url: str
    tool_count: int = 0


class PlatformServerCard(BaseModel):
    schema_version: str = "0.1.0"
    platform: str = "mcpworks"
    description: str = "Namespace-based function hosting for AI assistants"
    namespaces: list[NamespaceEntry] = Field(default_factory=list)
