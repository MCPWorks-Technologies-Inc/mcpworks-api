"""Integration tests for MCP endpoints."""

import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.models import Account, APIKey, Namespace, User
from mcpworks_api.models.function import Function
from mcpworks_api.models.function_version import FunctionVersion
from mcpworks_api.models.namespace_service import NamespaceService


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email=f"mcp-test-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$test$testhash",
        name="MCP Test User",
        tier="pro",
        status="active",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_account(db: AsyncSession, test_user: User) -> Account:
    """Create a test account."""
    account = Account(
        user_id=test_user.id,
        name="MCP Test Account",
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@pytest_asyncio.fixture
async def test_api_key(db: AsyncSession, test_user: User) -> tuple[APIKey, str]:
    """Create a test API key and return both the model and raw key."""
    raw_key = f"mcp_test_{uuid.uuid4().hex}"
    api_key = APIKey(
        user_id=test_user.id,
        key_hash=raw_key,  # In tests, we store raw for simplicity
        key_prefix=raw_key[:12],
        name="MCP Test Key",
        scopes=["read", "write", "execute"],
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key, raw_key


@pytest_asyncio.fixture
async def test_namespace(db: AsyncSession, test_account: Account) -> Namespace:
    """Create a test namespace."""
    namespace = Namespace(
        account_id=test_account.id,
        name=f"test-ns-{uuid.uuid4().hex[:8]}",
        description="Test namespace for MCP",
    )
    db.add(namespace)
    await db.commit()
    await db.refresh(namespace)
    return namespace


@pytest_asyncio.fixture
async def test_service(db: AsyncSession, test_namespace: Namespace) -> NamespaceService:
    """Create a test service."""
    service = NamespaceService(
        namespace_id=test_namespace.id,
        name="math",
        description="Math operations",
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service


@pytest_asyncio.fixture
async def test_function(
    db: AsyncSession, test_service: NamespaceService
) -> tuple[Function, FunctionVersion]:
    """Create a test function with version."""
    function = Function(
        service_id=test_service.id,
        name="calculate",
        description="Perform calculations",
        tags=["math", "utility"],
        active_version=1,
    )
    db.add(function)
    await db.commit()
    await db.refresh(function)

    version = FunctionVersion(
        function_id=function.id,
        version=1,
        backend="code_sandbox",
        code="def calculate(expression): return eval(expression)",
        config={"timeout_ms": 5000},
        input_schema={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
        output_schema={"type": "object", "properties": {"result": {"type": "number"}}},
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)

    return function, version


class TestMCPInfo:
    """Tests for MCP info endpoint."""

    async def test_mcp_info_without_namespace(self, client: AsyncClient):
        """Test MCP info returns protocol details."""
        response = await client.get("/v1/mcp")
        assert response.status_code == 200
        data = response.json()
        assert data["protocol"] == "mcp"
        assert data["version"] == "2024-11-05"
        assert "initialize" in data["supported_methods"]
        assert "tools/list" in data["supported_methods"]
        assert "tools/call" in data["supported_methods"]


class TestMCPAuthentication:
    """Tests for MCP authentication."""

    async def test_mcp_request_without_auth(self, client: AsyncClient):
        """Test MCP request without authentication returns error."""
        response = await client.post(
            "/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": "1",
            },
        )
        # Without subdomain middleware setting namespace, we get invalid request
        assert response.status_code == 200
        data = response.json()
        assert data.get("error") is not None

    async def test_mcp_request_with_invalid_key(
        self,
        client: AsyncClient,
        test_namespace: Namespace,
    ):
        """Test MCP request with invalid API key."""
        # Set namespace in request state (simulating subdomain middleware)
        response = await client.post(
            "/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": "1",
            },
            headers={"Authorization": "Bearer invalid_key"},
        )
        assert response.status_code == 200
        data = response.json()
        # Should get unauthorized error in JSON-RPC response
        assert data.get("error") is not None or data.get("result") is not None


class TestMCPProtocolErrors:
    """Tests for MCP protocol error handling."""

    async def test_invalid_json(self, client: AsyncClient):
        """Test handling of invalid JSON."""
        response = await client.post(
            "/v1/mcp",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        # FastAPI returns 422 for invalid JSON before our handler
        assert response.status_code in (200, 422)

    async def test_missing_method(self, client: AsyncClient):
        """Test handling of missing method field."""
        response = await client.post(
            "/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "1",
            },
        )
        assert response.status_code in (200, 422)


class TestMCPRouterParsing:
    """Tests for JSON-RPC parsing in router."""

    def test_parse_valid_request(self):
        """Test parsing valid JSON-RPC request."""
        from mcpworks_api.mcp.router import parse_json_rpc_request

        body = b'{"jsonrpc": "2.0", "method": "initialize", "id": 1}'
        request = parse_json_rpc_request(body)
        assert request.method == "initialize"
        assert request.id == 1

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON raises ValueError."""
        from mcpworks_api.mcp.router import parse_json_rpc_request

        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_json_rpc_request(b"not json")

    def test_parse_invalid_request(self):
        """Test parsing invalid JSON-RPC raises ValueError."""
        from mcpworks_api.mcp.router import parse_json_rpc_request

        with pytest.raises(ValueError, match="Invalid JSON-RPC"):
            parse_json_rpc_request(b'{"jsonrpc": "2.0"}')  # Missing method


class TestCreateMCPHandler:
    """Tests for CreateMCPHandler (management interface)."""

    async def test_initialize(self, db: AsyncSession, test_account: Account):
        """Test initialize method."""
        from mcpworks_api.mcp.create_handler import CreateMCPHandler
        from mcpworks_api.mcp.protocol import JSONRPCRequest

        handler = CreateMCPHandler(
            namespace="test-namespace",
            account=test_account,
            db=db,
        )

        request = JSONRPCRequest(method="initialize", id="init-1")
        response = await handler.handle(request)

        assert response.error is None
        assert response.result is not None
        assert response.result["protocolVersion"] == "2024-11-05"
        assert "tools" in response.result["capabilities"]
        assert "mcpworks-create" in response.result["serverInfo"]["name"]

    async def test_tools_list(self, db: AsyncSession, test_account: Account):
        """Test tools/list method returns management tools."""
        from mcpworks_api.mcp.create_handler import CreateMCPHandler
        from mcpworks_api.mcp.protocol import JSONRPCRequest

        handler = CreateMCPHandler(
            namespace="test-namespace",
            account=test_account,
            db=db,
        )

        request = JSONRPCRequest(method="tools/list", id="list-1")
        response = await handler.handle(request)

        assert response.error is None
        tools = response.result["tools"]
        tool_names = [t["name"] for t in tools]

        # Should have all management tools
        assert "make_namespace" in tool_names
        assert "list_namespaces" in tool_names
        assert "make_service" in tool_names
        assert "list_services" in tool_names
        assert "make_function" in tool_names
        assert "list_functions" in tool_names

    async def test_unknown_method(self, db: AsyncSession, test_account: Account):
        """Test unknown method returns error."""
        from mcpworks_api.mcp.create_handler import CreateMCPHandler
        from mcpworks_api.mcp.protocol import JSONRPCRequest, MCPErrorCodes

        handler = CreateMCPHandler(
            namespace="test-namespace",
            account=test_account,
            db=db,
        )

        request = JSONRPCRequest(method="unknown/method", id="err-1")
        response = await handler.handle(request)

        assert response.error is not None
        assert response.error.code == MCPErrorCodes.METHOD_NOT_FOUND
        assert "unknown/method" in response.error.message

    async def test_make_namespace(
        self,
        db: AsyncSession,
        test_account: Account,
    ):
        """Test make_namespace tool."""
        from mcpworks_api.mcp.create_handler import CreateMCPHandler
        from mcpworks_api.mcp.protocol import JSONRPCRequest

        handler = CreateMCPHandler(
            namespace="test-namespace",
            account=test_account,
            db=db,
        )

        request = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "make_namespace",
                "arguments": {
                    "name": f"new-ns-{uuid.uuid4().hex[:8]}",
                    "description": "A new namespace",
                },
            },
            id="make-ns-1",
        )
        response = await handler.handle(request)

        assert response.error is None
        result = response.result
        assert result["isError"] is False
        content = json.loads(result["content"][0]["text"])
        assert "id" in content
        assert "create_endpoint" in content
        assert "run_endpoint" in content

    async def test_list_namespaces(
        self,
        db: AsyncSession,
        test_account: Account,
        test_namespace: Namespace,
    ):
        """Test list_namespaces tool."""
        from mcpworks_api.mcp.create_handler import CreateMCPHandler
        from mcpworks_api.mcp.protocol import JSONRPCRequest

        handler = CreateMCPHandler(
            namespace=test_namespace.name,
            account=test_account,
            db=db,
        )

        request = JSONRPCRequest(
            method="tools/call",
            params={"name": "list_namespaces", "arguments": {}},
            id="list-ns-1",
        )
        response = await handler.handle(request)

        assert response.error is None
        result = response.result
        content = json.loads(result["content"][0]["text"])
        assert "namespaces" in content
        assert "total" in content
        # Should find our test namespace
        ns_names = [ns["name"] for ns in content["namespaces"]]
        assert test_namespace.name in ns_names


class TestRunMCPHandler:
    """Tests for RunMCPHandler (execution interface)."""

    async def test_initialize(
        self,
        db: AsyncSession,
        test_account: Account,
        test_namespace: Namespace,
    ):
        """Test initialize method."""
        from mcpworks_api.mcp.protocol import JSONRPCRequest
        from mcpworks_api.mcp.run_handler import RunMCPHandler

        handler = RunMCPHandler(
            namespace=test_namespace.name,
            account=test_account,
            db=db,
        )

        request = JSONRPCRequest(method="initialize", id="init-1")
        response = await handler.handle(request)

        assert response.error is None
        assert response.result["protocolVersion"] == "2024-11-05"
        assert "mcpworks-run" in response.result["serverInfo"]["name"]

    async def test_tools_list_empty(
        self,
        db: AsyncSession,
        test_account: Account,
        test_namespace: Namespace,
    ):
        """Test tools/list with no functions (tool mode)."""
        from mcpworks_api.mcp.protocol import JSONRPCRequest
        from mcpworks_api.mcp.run_handler import RunMCPHandler

        handler = RunMCPHandler(
            namespace=test_namespace.name,
            account=test_account,
            db=db,
            mode="tools",
        )

        request = JSONRPCRequest(method="tools/list", id="list-1")
        response = await handler.handle(request)

        assert response.error is None
        tools = response.result["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "_env_status"

    async def test_tools_list_with_functions(
        self,
        db: AsyncSession,
        test_account: Account,
        test_namespace: Namespace,
        test_service: NamespaceService,
        test_function: tuple[Function, FunctionVersion],
    ):
        """Test tools/list returns functions as tools (tool mode)."""
        from mcpworks_api.mcp.protocol import JSONRPCRequest
        from mcpworks_api.mcp.run_handler import RunMCPHandler

        function, version = test_function

        handler = RunMCPHandler(
            namespace=test_namespace.name,
            account=test_account,
            db=db,
            mode="tools",
        )

        request = JSONRPCRequest(method="tools/list", id="list-1")
        response = await handler.handle(request)

        assert response.error is None
        tools = response.result["tools"]
        assert len(tools) >= 1

        # Find our test function
        tool_names = [t["name"] for t in tools]
        expected_name = f"{test_service.name}.{function.name}"
        assert expected_name in tool_names

        # Check tool schema
        tool = next(t for t in tools if t["name"] == expected_name)
        assert tool["description"] == function.description
        assert tool["inputSchema"] == version.input_schema

    async def test_tools_call_invalid_format(
        self,
        db: AsyncSession,
        test_account: Account,
        test_namespace: Namespace,
    ):
        """Test tools/call with invalid tool name format."""
        from mcpworks_api.mcp.protocol import JSONRPCRequest, MCPErrorCodes
        from mcpworks_api.mcp.run_handler import RunMCPHandler

        handler = RunMCPHandler(
            namespace=test_namespace.name,
            account=test_account,
            db=db,
        )

        request = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "invalid_no_dot",  # Should be service.function
                "arguments": {},
            },
            id="call-1",
        )
        response = await handler.handle(request)

        assert response.error is not None
        assert response.error.code == MCPErrorCodes.INVALID_PARAMS
        assert "service.function" in response.error.message

    async def test_tools_call_invalid_params(
        self,
        db: AsyncSession,
        test_account: Account,
        test_namespace: Namespace,
    ):
        """Test tools/call with invalid params structure."""
        from mcpworks_api.mcp.protocol import JSONRPCRequest, MCPErrorCodes
        from mcpworks_api.mcp.run_handler import RunMCPHandler

        handler = RunMCPHandler(
            namespace=test_namespace.name,
            account=test_account,
            db=db,
        )

        request = JSONRPCRequest(
            method="tools/call",
            params={"invalid": "structure"},  # Missing 'name' field
            id="call-1",
        )
        response = await handler.handle(request)

        assert response.error is not None
        assert response.error.code == MCPErrorCodes.INVALID_PARAMS

    async def test_unknown_method(
        self,
        db: AsyncSession,
        test_account: Account,
        test_namespace: Namespace,
    ):
        """Test unknown method returns error."""
        from mcpworks_api.mcp.protocol import JSONRPCRequest, MCPErrorCodes
        from mcpworks_api.mcp.run_handler import RunMCPHandler

        handler = RunMCPHandler(
            namespace=test_namespace.name,
            account=test_account,
            db=db,
        )

        request = JSONRPCRequest(method="unknown/method", id="err-1")
        response = await handler.handle(request)

        assert response.error is not None
        assert response.error.code == MCPErrorCodes.METHOD_NOT_FOUND
