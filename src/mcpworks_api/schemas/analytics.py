"""Pydantic schemas for MCP proxy analytics responses."""

from pydantic import BaseModel, Field


class ToolStats(BaseModel):
    name: str
    calls: int
    avg_latency_ms: float
    avg_response_bytes: float
    avg_response_tokens_est: float
    error_count: int
    timeout_count: int
    truncation_count: int
    injections_detected: int


class ServerStatsResponse(BaseModel):
    server: str
    period: str
    total_calls: int
    total_errors: int
    error_rate: float
    tools: list[ToolStats] = Field(default_factory=list)


class TopConsumer(BaseModel):
    server: str
    tool: str
    bytes: int


class TokenSavingsResponse(BaseModel):
    period: str
    total_executions: int = 0
    input_bytes: int = 0
    input_tokens_est: int = 0
    mcp_data_processed_bytes: int = 0
    mcp_data_processed_tokens_est: int = 0
    result_returned_bytes: int = 0
    result_returned_tokens_est: int = 0
    tokens_saved_est: int = 0
    savings_percent: float = 0.0
    top_consumers: list[TopConsumer] = Field(default_factory=list)


class Suggestion(BaseModel):
    type: str
    server: str
    tool: str | None = None
    reason: str
    action: str
    estimated_savings_percent: float | None = None
    estimated_impact: str | None = None


class SuggestionResponse(BaseModel):
    suggestions: list[Suggestion] = Field(default_factory=list)


class TopNamespace(BaseModel):
    namespace_id: str
    tokens_saved: int
    executions: int


class PlatformTokenSavingsResponse(BaseModel):
    period: str
    total_executions: int = 0
    active_namespaces: int = 0
    input_bytes: int = 0
    input_tokens_est: int = 0
    mcp_data_processed_bytes: int = 0
    mcp_data_processed_tokens_est: int = 0
    result_returned_bytes: int = 0
    result_returned_tokens_est: int = 0
    tokens_saved_est: int = 0
    savings_percent: float = 0.0
    top_namespaces: list[TopNamespace] = Field(default_factory=list)


class FunctionMcpStatsResponse(BaseModel):
    function: str
    period: str
    executions: int
    avg_mcp_calls_per_execution: float
    avg_mcp_bytes_per_execution: float
    avg_result_bytes: float
    avg_tokens_saved: float
