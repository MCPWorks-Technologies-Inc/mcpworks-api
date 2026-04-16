"""Unit tests for MCP server card discovery schemas and response shaping."""

from mcpworks_api.schemas.discovery import (
    EndpointsInfo,
    NamespaceEntry,
    NamespaceServerCard,
    PlatformServerCard,
    ToolSummary,
)


class TestNamespaceServerCard:
    def test_minimal_card(self):
        card = NamespaceServerCard(
            name="test",
            endpoints=EndpointsInfo(
                create="https://test.create.mcpworks.io/mcp",
                run="https://test.run.mcpworks.io/mcp",
            ),
        )
        assert card.name == "test"
        assert card.schema_version == "0.1.0"
        assert card.protocol_version == "2024-11-05"
        assert card.tools == []
        assert card.private_tool_count == 0
        assert card.total_tool_count == 0
        assert card.service_count == 0
        assert len(card.transports) == 1
        assert card.transports[0].type == "https+sse"

    def test_card_with_tools(self):
        card = NamespaceServerCard(
            name="busybox",
            description="Test namespace",
            endpoints=EndpointsInfo(
                create="https://busybox.create.mcpworks.io/mcp",
                run="https://busybox.run.mcpworks.io/mcp",
            ),
            tools=[
                ToolSummary(
                    name="check-api",
                    description="Health check",
                    input_schema={"type": "object", "properties": {}},
                ),
            ],
            private_tool_count=5,
            service_count=2,
            total_tool_count=6,
        )
        assert len(card.tools) == 1
        assert card.tools[0].name == "check-api"
        assert card.private_tool_count == 5
        assert card.total_tool_count == 6

    def test_card_serialization(self):
        card = NamespaceServerCard(
            name="test",
            endpoints=EndpointsInfo(
                create="https://test.create.mcpworks.io/mcp",
                run="https://test.run.mcpworks.io/mcp",
            ),
        )
        data = card.model_dump()
        assert data["schema_version"] == "0.1.0"
        assert data["endpoints"]["create"] == "https://test.create.mcpworks.io/mcp"
        assert "tools" in data
        assert "private_tool_count" in data

    def test_card_with_null_description(self):
        card = NamespaceServerCard(
            name="test",
            description=None,
            endpoints=EndpointsInfo(
                create="https://test.create.mcpworks.io/mcp",
                run="https://test.run.mcpworks.io/mcp",
            ),
        )
        assert card.description is None


class TestPlatformServerCard:
    def test_empty_platform_card(self):
        card = PlatformServerCard()
        assert card.schema_version == "0.1.0"
        assert card.platform == "mcpworks"
        assert card.namespaces == []

    def test_platform_card_with_namespaces(self):
        card = PlatformServerCard(
            namespaces=[
                NamespaceEntry(
                    name="busybox",
                    description="Test",
                    server_card_url="https://busybox.create.mcpworks.io/.well-known/mcp.json",
                    tool_count=10,
                ),
                NamespaceEntry(
                    name="simon",
                    server_card_url="https://simon.create.mcpworks.io/.well-known/mcp.json",
                    tool_count=0,
                ),
            ]
        )
        assert len(card.namespaces) == 2
        assert card.namespaces[0].name == "busybox"
        assert card.namespaces[0].tool_count == 10
        assert card.namespaces[1].description is None

    def test_platform_card_serialization(self):
        card = PlatformServerCard(
            namespaces=[
                NamespaceEntry(
                    name="test",
                    server_card_url="https://test.create.mcpworks.io/.well-known/mcp.json",
                    tool_count=3,
                ),
            ]
        )
        data = card.model_dump()
        assert data["platform"] == "mcpworks"
        assert len(data["namespaces"]) == 1
        assert data["namespaces"][0]["server_card_url"].endswith(".well-known/mcp.json")


class TestToolSummary:
    def test_tool_with_schema(self):
        tool = ToolSummary(
            name="hello",
            description="Say hello",
            input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
        )
        assert tool.name == "hello"
        assert tool.input_schema is not None

    def test_tool_without_schema(self):
        tool = ToolSummary(name="ping")
        assert tool.description is None
        assert tool.input_schema is None
