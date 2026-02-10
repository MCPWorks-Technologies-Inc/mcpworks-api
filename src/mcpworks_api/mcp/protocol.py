"""MCP Protocol (JSON-RPC 2.0) helpers.

Implements the Model Context Protocol for AI assistant communication.
Based on the MCP specification: https://spec.modelcontextprotocol.io/
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request."""

    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 error."""

    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None
    id: Optional[Union[str, int]] = None


class MCPTool(BaseModel):
    """MCP tool definition."""

    name: str
    description: str
    inputSchema: Dict[str, Any]


class MCPToolsListResult(BaseModel):
    """Result of tools/list method."""

    tools: List[MCPTool]


class MCPToolCallParams(BaseModel):
    """Parameters for tools/call method."""

    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class MCPContent(BaseModel):
    """MCP content block."""

    type: str = "text"
    text: str


class MCPToolResult(BaseModel):
    """Result of tools/call method."""

    content: List[MCPContent]
    isError: bool = False
    metadata: Optional[Dict[str, Any]] = None


class MCPErrorCodes:
    """Standard JSON-RPC 2.0 and custom MCP error codes."""

    # Standard JSON-RPC 2.0 errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Custom MCP errors
    UNAUTHORIZED = -32001
    FORBIDDEN = -32002
    NOT_FOUND = -32003
    RATE_LIMITED = -32004
    QUOTA_EXCEEDED = -32005
    EXECUTION_ERROR = -32006
    NETWORK_BLOCKED = -32007
    WHITELIST_RATE_LIMITED = -32008


def make_error_response(
    code: int,
    message: str,
    data: Any = None,
    request_id: Optional[Union[str, int]] = None,
) -> JSONRPCResponse:
    """Create a JSON-RPC error response."""
    return JSONRPCResponse(
        error=JSONRPCError(code=code, message=message, data=data),
        id=request_id,
    )


def make_success_response(
    result: Any,
    request_id: Optional[Union[str, int]] = None,
) -> JSONRPCResponse:
    """Create a JSON-RPC success response."""
    return JSONRPCResponse(result=result, id=request_id)


def make_tool_result(
    text: str,
    is_error: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> MCPToolResult:
    """Create an MCP tool result."""
    return MCPToolResult(
        content=[MCPContent(text=text)],
        isError=is_error,
        metadata=metadata,
    )
