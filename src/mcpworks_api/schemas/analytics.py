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
    mcp_data_processed_bytes: int
    mcp_data_processed_tokens_est: int
    result_returned_bytes: int
    result_returned_tokens_est: int
    savings_percent: float
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


class FunctionMcpStatsResponse(BaseModel):
    function: str
    period: str
    executions: int
    avg_mcp_calls_per_execution: float
    avg_mcp_bytes_per_execution: float
    avg_result_bytes: float
    avg_tokens_saved: float
