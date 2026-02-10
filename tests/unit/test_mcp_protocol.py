"""Tests for MCP protocol helpers."""

import pytest

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


class TestJSONRPCRequest:
    """Tests for JSONRPCRequest model."""

    def test_request_with_all_fields(self):
        """Test creating request with all fields."""
        req = JSONRPCRequest(
            jsonrpc="2.0",
            method="tools/list",
            params={"key": "value"},
            id="req-123",
        )
        assert req.jsonrpc == "2.0"
        assert req.method == "tools/list"
        assert req.params == {"key": "value"}
        assert req.id == "req-123"

    def test_request_minimal(self):
        """Test creating request with minimal fields."""
        req = JSONRPCRequest(method="initialize")
        assert req.jsonrpc == "2.0"
        assert req.method == "initialize"
        assert req.params is None
        assert req.id is None

    def test_request_with_integer_id(self):
        """Test request with integer ID."""
        req = JSONRPCRequest(method="test", id=42)
        assert req.id == 42

    def test_request_serialization(self):
        """Test request serializes correctly."""
        req = JSONRPCRequest(method="tools/call", params={"name": "test"}, id="1")
        data = req.model_dump()
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "tools/call"
        assert data["params"] == {"name": "test"}
        assert data["id"] == "1"


class TestJSONRPCResponse:
    """Tests for JSONRPCResponse model."""

    def test_success_response(self):
        """Test creating success response."""
        resp = JSONRPCResponse(
            result={"status": "ok"},
            id="req-123",
        )
        assert resp.jsonrpc == "2.0"
        assert resp.result == {"status": "ok"}
        assert resp.error is None
        assert resp.id == "req-123"

    def test_error_response(self):
        """Test creating error response."""
        error = JSONRPCError(code=-32600, message="Invalid Request")
        resp = JSONRPCResponse(error=error, id="req-123")
        assert resp.result is None
        assert resp.error.code == -32600
        assert resp.error.message == "Invalid Request"

    def test_error_with_data(self):
        """Test error response with data field."""
        error = JSONRPCError(
            code=-32602,
            message="Invalid params",
            data={"field": "name", "reason": "required"},
        )
        resp = JSONRPCResponse(error=error, id=1)
        assert resp.error.data == {"field": "name", "reason": "required"}


class TestMCPModels:
    """Tests for MCP-specific models."""

    def test_mcp_tool(self):
        """Test MCPTool model."""
        tool = MCPTool(
            name="calculate",
            description="Perform calculations",
            inputSchema={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        )
        assert tool.name == "calculate"
        assert tool.description == "Perform calculations"
        assert "expression" in tool.inputSchema["properties"]

    def test_mcp_tools_list_result(self):
        """Test MCPToolsListResult model."""
        tools = [
            MCPTool(name="tool1", description="First tool", inputSchema={}),
            MCPTool(name="tool2", description="Second tool", inputSchema={}),
        ]
        result = MCPToolsListResult(tools=tools)
        assert len(result.tools) == 2
        assert result.tools[0].name == "tool1"

    def test_mcp_tool_call_params(self):
        """Test MCPToolCallParams model."""
        params = MCPToolCallParams(
            name="math.calculate",
            arguments={"expression": "2 + 2"},
        )
        assert params.name == "math.calculate"
        assert params.arguments == {"expression": "2 + 2"}

    def test_mcp_tool_call_params_default_arguments(self):
        """Test MCPToolCallParams with default arguments."""
        params = MCPToolCallParams(name="test.tool")
        assert params.arguments == {}

    def test_mcp_content(self):
        """Test MCPContent model."""
        content = MCPContent(text="Hello, world!")
        assert content.type == "text"
        assert content.text == "Hello, world!"

    def test_mcp_tool_result(self):
        """Test MCPToolResult model."""
        result = MCPToolResult(
            content=[MCPContent(text="Result: 4")],
            isError=False,
            metadata={"execution_time_ms": 42},
        )
        assert len(result.content) == 1
        assert result.content[0].text == "Result: 4"
        assert result.isError is False
        assert result.metadata["execution_time_ms"] == 42

    def test_mcp_tool_result_error(self):
        """Test MCPToolResult for errors."""
        result = MCPToolResult(
            content=[MCPContent(text="Error: Division by zero")],
            isError=True,
        )
        assert result.isError is True


class TestMCPErrorCodes:
    """Tests for MCP error codes."""

    def test_standard_json_rpc_errors(self):
        """Test standard JSON-RPC error codes."""
        assert MCPErrorCodes.PARSE_ERROR == -32700
        assert MCPErrorCodes.INVALID_REQUEST == -32600
        assert MCPErrorCodes.METHOD_NOT_FOUND == -32601
        assert MCPErrorCodes.INVALID_PARAMS == -32602
        assert MCPErrorCodes.INTERNAL_ERROR == -32603

    def test_custom_mcp_errors(self):
        """Test custom MCP error codes."""
        assert MCPErrorCodes.UNAUTHORIZED == -32001
        assert MCPErrorCodes.FORBIDDEN == -32002
        assert MCPErrorCodes.NOT_FOUND == -32003
        assert MCPErrorCodes.RATE_LIMITED == -32004
        assert MCPErrorCodes.QUOTA_EXCEEDED == -32005
        assert MCPErrorCodes.EXECUTION_ERROR == -32006


class TestHelperFunctions:
    """Tests for protocol helper functions."""

    def test_make_error_response(self):
        """Test make_error_response helper."""
        resp = make_error_response(
            code=MCPErrorCodes.NOT_FOUND,
            message="Resource not found",
            data={"resource": "function"},
            request_id="req-456",
        )
        assert resp.jsonrpc == "2.0"
        assert resp.error.code == -32003
        assert resp.error.message == "Resource not found"
        assert resp.error.data == {"resource": "function"}
        assert resp.id == "req-456"
        assert resp.result is None

    def test_make_error_response_minimal(self):
        """Test make_error_response with minimal args."""
        resp = make_error_response(
            code=MCPErrorCodes.INTERNAL_ERROR,
            message="Server error",
        )
        assert resp.error.code == -32603
        assert resp.error.data is None
        assert resp.id is None

    def test_make_success_response(self):
        """Test make_success_response helper."""
        resp = make_success_response(
            result={"tools": []},
            request_id="req-789",
        )
        assert resp.jsonrpc == "2.0"
        assert resp.result == {"tools": []}
        assert resp.id == "req-789"
        assert resp.error is None

    def test_make_success_response_minimal(self):
        """Test make_success_response with minimal args."""
        resp = make_success_response(result=None)
        assert resp.result is None
        assert resp.id is None

    def test_make_tool_result(self):
        """Test make_tool_result helper."""
        result = make_tool_result(
            text="Operation completed",
            is_error=False,
            metadata={"duration": 100},
        )
        assert len(result.content) == 1
        assert result.content[0].text == "Operation completed"
        assert result.isError is False
        assert result.metadata == {"duration": 100}

    def test_make_tool_result_error(self):
        """Test make_tool_result for errors."""
        result = make_tool_result(
            text="Failed to execute",
            is_error=True,
        )
        assert result.isError is True
        assert result.metadata is None
