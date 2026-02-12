"""MCP Protocol Layer - JSON-RPC 2.0 handlers for AI assistant communication.

This module provides:
- JSON-RPC 2.0 protocol implementation (protocol.py)
- Create handler for management operations (create_handler.py)
- Run handler for function execution (run_handler.py)
- Streamable HTTP transport via MCP SDK (transport.py)
- Legacy FastAPI router for MCP endpoints (router.py)

Usage:
    In main.py:
        from mcpworks_api.mcp.transport import MCPTransportMiddleware, session_manager
        app.mount("/mcp", mcp_asgi_app)
"""

from mcpworks_api.mcp.create_handler import CreateMCPHandler
from mcpworks_api.mcp.protocol import (
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPContent,
    MCPErrorCodes,
    MCPTool,
    MCPToolCallParams,
    MCPToolResult,
    MCPToolsListResult,
    make_error_response,
    make_success_response,
    make_tool_result,
)
from mcpworks_api.mcp.router import router as mcp_router
from mcpworks_api.mcp.run_handler import RunMCPHandler
from mcpworks_api.mcp.transport import MCPTransportMiddleware, session_manager

__all__ = [
    # Protocol
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCError",
    "MCPTool",
    "MCPToolsListResult",
    "MCPToolCallParams",
    "MCPContent",
    "MCPToolResult",
    "MCPErrorCodes",
    "make_error_response",
    "make_success_response",
    "make_tool_result",
    # Handlers
    "CreateMCPHandler",
    "RunMCPHandler",
    # Transport
    "MCPTransportMiddleware",
    "session_manager",
    # Legacy Router
    "mcp_router",
]
