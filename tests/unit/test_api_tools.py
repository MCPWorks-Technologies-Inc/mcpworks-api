"""Unit tests for published-API-tool helpers (019, T030/T033)."""

from mcpworks_api.core.api_proxy import build_published_api_tool, parse_api_tool_name


def test_parse_round_trips() -> None:
    assert parse_api_tool_name("api__acme__list_orders") == ("acme", "list_orders")
    # Server names may contain hyphens; operation_ids may contain underscores.
    assert parse_api_tool_name("api__acme-prod__get_order_2") == ("acme-prod", "get_order_2")


def test_parse_rejects_non_api_and_malformed() -> None:
    assert parse_api_tool_name("execute_python") is None
    assert parse_api_tool_name("svc__fn") is None  # no api__ prefix
    assert parse_api_tool_name("api__noop") is None  # missing second __
    assert parse_api_tool_name("api__") is None


def test_build_tool_name_and_schema() -> None:
    ep = {
        "operation_id": "get_order",
        "method": "GET",
        "path": "/orders/{id}",
        "summary": "Get an order",
        "param_schema": {
            "path": {"type": "object", "properties": {"id": {"type": "string"}}},
            "query": {"type": "object", "properties": {}},
        },
        "request_body_schema": None,
    }
    tool = build_published_api_tool("acme", ep)
    assert tool["name"] == "api__acme__get_order"
    assert "raw API response" in tool["description"]
    props = tool["inputSchema"]["properties"]
    assert props["path"]["properties"]["id"]["type"] == "string"
    assert props["query"] == {"type": "object", "properties": {}}
    assert "body" not in props  # no request body → no body arg
    # The generated name parses back to the same (server, op).
    assert parse_api_tool_name(tool["name"]) == ("acme", "get_order")


def test_build_tool_includes_body_when_present() -> None:
    ep = {
        "operation_id": "create_order",
        "method": "POST",
        "path": "/orders",
        "request_body_schema": {"type": "object", "properties": {"sku": {"type": "string"}}},
    }
    tool = build_published_api_tool("acme", ep)
    assert tool["inputSchema"]["properties"]["body"]["properties"]["sku"]["type"] == "string"


def test_build_tool_defaults_for_sparse_endpoint() -> None:
    tool = build_published_api_tool("svc", {"operation_id": "ping", "method": "GET", "path": "/p"})
    props = tool["inputSchema"]["properties"]
    assert props["path"] == {"type": "object"}
    assert props["query"] == {"type": "object"}
    assert props["headers"] == {"type": "object"}
