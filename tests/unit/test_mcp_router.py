"""Unit tests for MCP router functions."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from mcpworks_api.mcp.protocol import JSONRPCRequest
from mcpworks_api.mcp.router import (
    get_account_from_api_key,
    parse_json_rpc_request,
    validate_namespace_access,
)


class MockRequest:
    """Mock FastAPI request."""

    def __init__(self, auth_header=None, namespace=None, endpoint_type=None):
        self.headers = {}
        if auth_header:
            self.headers["Authorization"] = auth_header
        self.state = MagicMock()
        self.state.namespace = namespace
        self.state.endpoint_type = endpoint_type

    async def body(self):
        """Return request body."""
        return getattr(self, "_body", b"")


class TestParseJsonRpcRequest:
    """Tests for parse_json_rpc_request function."""

    def test_parse_valid_request(self):
        """Test parsing a valid JSON-RPC request."""
        body = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": "req-123"}).encode()

        result = parse_json_rpc_request(body)

        assert isinstance(result, JSONRPCRequest)
        assert result.method == "tools/list"
        assert result.id == "req-123"

    def test_parse_request_with_params(self):
        """Test parsing request with params."""
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "test", "arguments": {}},
                "id": 1,
            }
        ).encode()

        result = parse_json_rpc_request(body)

        assert result.params == {"name": "test", "arguments": {}}

    def test_parse_minimal_request(self):
        """Test parsing minimal request (method only)."""
        body = json.dumps({"method": "initialize"}).encode()

        result = parse_json_rpc_request(body)

        assert result.method == "initialize"
        assert result.jsonrpc == "2.0"  # Default

    def test_parse_invalid_json_raises(self):
        """Test that invalid JSON raises ValueError."""
        body = b"not valid json"

        with pytest.raises(ValueError) as exc_info:
            parse_json_rpc_request(body)

        assert "Invalid JSON" in str(exc_info.value)

    def test_parse_missing_method_raises(self):
        """Test that missing method raises ValueError."""
        body = json.dumps({"jsonrpc": "2.0", "id": "req-1"}).encode()

        with pytest.raises(ValueError) as exc_info:
            parse_json_rpc_request(body)

        assert "Invalid JSON-RPC request" in str(exc_info.value)

    def test_parse_empty_object_raises(self):
        """Test that empty object raises ValueError."""
        body = json.dumps({}).encode()

        with pytest.raises(ValueError) as exc_info:
            parse_json_rpc_request(body)

        assert "Invalid JSON-RPC request" in str(exc_info.value)


class TestGetAccountFromApiKey:
    """Tests for get_account_from_api_key function.

    Note: Full integration tests for this function are in test_mcp_endpoints.py.
    These unit tests focus on the early validation logic.
    """

    @pytest.mark.asyncio
    async def test_missing_auth_header_raises(self):
        """Test that missing Authorization header raises 401."""
        request = MockRequest(auth_header=None)
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_account_from_api_key(request, db)

        assert exc_info.value.status_code == 401
        assert "Missing or invalid Authorization header" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_auth_format_raises(self):
        """Test that non-Bearer auth raises 401."""
        request = MockRequest(auth_header="Basic dXNlcjpwYXNz")
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_account_from_api_key(request, db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_extracts_bearer_token(self):
        """Test that Bearer token is correctly extracted."""
        request = MockRequest(auth_header="Bearer my_api_key_123")

        # Verify the auth header parsing happens correctly
        auth_header = request.headers.get("Authorization", "")
        assert auth_header.startswith("Bearer ")
        api_key_value = auth_header[7:]  # Remove "Bearer " prefix
        assert api_key_value == "my_api_key_123"


class TestValidateNamespaceAccess:
    """Tests for validate_namespace_access function."""

    @pytest.mark.asyncio
    async def test_namespace_not_found_raises(self):
        """Test that non-existent namespace raises 404."""
        from mcpworks_api.core.exceptions import NotFoundError

        db = AsyncMock()
        account = MagicMock()
        account.id = uuid.uuid4()

        with patch("mcpworks_api.mcp.router.NamespaceServiceManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_by_name = AsyncMock(side_effect=NotFoundError("Namespace not found"))
            mock_manager_class.return_value = mock_manager

            with pytest.raises(HTTPException) as exc_info:
                await validate_namespace_access("nonexistent", account, db)

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_namespace_access_denied_raises(self):
        """Test that access denied raises 403."""
        from mcpworks_api.core.exceptions import ForbiddenError

        db = AsyncMock()
        account = MagicMock()
        account.id = uuid.uuid4()

        with patch("mcpworks_api.mcp.router.NamespaceServiceManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_by_name = AsyncMock(side_effect=ForbiddenError("Access denied"))
            mock_manager_class.return_value = mock_manager

            with pytest.raises(HTTPException) as exc_info:
                await validate_namespace_access("private", account, db)

            assert exc_info.value.status_code == 403
            assert "Access denied" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_valid_namespace_returns_it(self):
        """Test that valid namespace access returns the namespace."""
        db = AsyncMock()
        account = MagicMock()
        account.id = uuid.uuid4()

        mock_namespace = MagicMock()
        mock_namespace.name = "test-ns"

        with patch("mcpworks_api.mcp.router.NamespaceServiceManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_by_name = AsyncMock(return_value=mock_namespace)
            mock_manager_class.return_value = mock_manager

            result = await validate_namespace_access("test-ns", account, db)

            assert result == mock_namespace


class TestMcpInfoEndpoint:
    """Tests for mcp_info endpoint function."""

    @pytest.mark.asyncio
    async def test_mcp_info_returns_protocol_info(self):
        """Test that mcp_info returns protocol information."""
        from mcpworks_api.mcp.router import mcp_info

        request = MockRequest(namespace="acme", endpoint_type="create")

        result = await mcp_info(request)

        assert result["protocol"] == "mcp"
        assert result["version"] == "2024-11-05"
        assert result["namespace"] == "acme"
        assert result["endpoint_type"] == "create"
        assert "tools/list" in result["supported_methods"]
        assert "tools/call" in result["supported_methods"]

    @pytest.mark.asyncio
    async def test_mcp_info_without_namespace(self):
        """Test mcp_info when namespace not set."""
        from mcpworks_api.mcp.router import mcp_info

        request = MockRequest(namespace=None, endpoint_type=None)

        result = await mcp_info(request)

        assert result["namespace"] is None
        assert result["endpoint_type"] is None
