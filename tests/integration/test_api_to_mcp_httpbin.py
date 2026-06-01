"""Live end-to-end test for API → MCP against httpbin.org (feature 019, T023/T031).

Drives the full DB-backed proxy path against a REAL public API:
register (OpenAPI import) → curate (enable) → proxy_api_call → real upstream.
Covers stored + passthrough credential injection and namespace scoping — the
complete path minus the sandbox subprocess (which needs a running API server to
call back into; that variant is an out-of-band e2e).

Requires BOTH Postgres (the ``db`` fixture) AND outbound network. SKIPPED by
default; enable with:

    RUN_LIVE_TESTS=1 pytest tests/integration/test_api_to_mcp_httpbin.py -m network
"""

import os
import uuid

import pytest

from mcpworks_api.core.exec_token_registry import (
    register_execution,
    resolve_execution,
    unregister_execution,
)
from mcpworks_api.models import Account, Namespace, User
from mcpworks_api.services.api_server import ApiServerService

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        not os.getenv("RUN_LIVE_TESTS"),
        reason="live network + DB test; set RUN_LIVE_TESTS=1 to run",
    ),
]

HTTPBIN_SPEC_URL = "https://httpbin.org/spec.json"


@pytest.fixture
async def namespace(db):
    user = User(
        email=f"e2e-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        name="E2E User",
        tier="builder",
        status="active",
    )
    db.add(user)
    await db.flush()
    account = Account(user_id=user.id, name="E2E Acct")
    db.add(account)
    await db.flush()
    ns = Namespace(account_id=account.id, name=f"e2e-{uuid.uuid4().hex[:8]}")
    db.add(ns)
    await db.flush()
    return ns


async def _enable_by_path(svc, ns_id, server, method, path) -> str:
    """Find an endpoint by (method, path) and enable it; return its operation_id."""
    endpoints = await svc.list_endpoints(ns_id, server)
    match = next(e for e in endpoints if e.method == method and e.path == path)
    await svc.set_enabled(ns_id, server, [match.operation_id], enabled=True)
    return match.operation_id


async def test_register_import_curate_and_proxy_stored_bearer(db, namespace):
    svc = ApiServerService(db)
    # Register via REAL OpenAPI import (SSRF-checked fetch of httpbin's spec).
    server, endpoints, dropped = await svc.add_server(
        namespace_id=namespace.id,
        name="httpbin",
        base_url="https://httpbin.org",
        spec_source="openapi_url",
        openapi_url=HTTPBIN_SPEC_URL,
        auth=[
            {
                "name": "token",
                "location": "bearer",
                "format": "Bearer {value}",
                "source": "stored",
                "value": "sk_live_e2e_TOKEN",
            }
        ],
    )
    assert server.endpoint_count > 30
    assert all(not e.enabled for e in endpoints)  # imported → disabled (curation)

    op = await _enable_by_path(svc, namespace.id, "httpbin", "GET", "/bearer")

    # Drive the proxy directly (DB resolution → cred injection → SSRF → real call).
    token = "bridge_" + uuid.uuid4().hex
    register_execution(
        token=token,
        namespace_id=namespace.id,
        namespace_name=namespace.name,
        execution_id=str(uuid.uuid4()),
    )
    try:
        from mcpworks_api.core.api_proxy import proxy_api_call

        ctx = resolve_execution(token)
        result = await proxy_api_call(
            ctx=ctx,
            server_name="httpbin",
            operation_id=op,
            path={},
            query={},
            body=None,
            headers={},
            db=db,
        )
    finally:
        unregister_execution(token)

    assert result.error is None
    assert result.status_code == 200
    # httpbin /bearer confirms the injected stored bearer credential reached it.
    assert result.json_body["authenticated"] is True
    assert result.json_body["token"] == "sk_live_e2e_TOKEN"


async def test_proxy_passthrough_and_query_and_scoping(db, namespace):
    svc = ApiServerService(db)
    await svc.add_server(
        namespace_id=namespace.id,
        name="httpbin",
        base_url="https://httpbin.org",
        spec_source="openapi_url",
        openapi_url=HTTPBIN_SPEC_URL,
        auth=[
            {
                "name": "api",
                "location": "header",
                "key": "X-Api-Key",
                "format": "{value}",
                "source": "passthrough",
                "env_var": "ACME_KEY",
            }
        ],
    )
    op_headers = await _enable_by_path(svc, namespace.id, "httpbin", "GET", "/headers")
    op_get = await _enable_by_path(svc, namespace.id, "httpbin", "GET", "/get")

    token = "bridge_" + uuid.uuid4().hex
    # Passthrough value supplied at the execution boundary, not by sandbox code.
    register_execution(
        token=token,
        namespace_id=namespace.id,
        namespace_name=namespace.name,
        execution_id=str(uuid.uuid4()),
        passthrough_env={"ACME_KEY": "passthru_e2e"},
    )
    try:
        from mcpworks_api.core.api_proxy import proxy_api_call

        ctx = resolve_execution(token)

        # Passthrough header injected server-side and echoed by httpbin.
        r1 = await proxy_api_call(ctx, "httpbin", op_headers, {}, {}, None, {}, db)
        assert r1.error is None
        assert r1.json_body["headers"].get("X-Api-Key") == "passthru_e2e"

        # Query params reach the upstream.
        r2 = await proxy_api_call(ctx, "httpbin", op_get, {}, {"q": "hello"}, None, {}, db)
        assert r2.json_body["args"] == {"q": "hello"}

        # Cross-namespace / unknown server is rejected, not proxied.
        r3 = await proxy_api_call(ctx, "does-not-exist", op_get, {}, {}, None, {}, db)
        assert r3.error == "endpoint_not_found"
    finally:
        unregister_execution(token)


async def test_proxy_rejects_disabled_endpoint(db, namespace):
    svc = ApiServerService(db)
    await svc.add_server(
        namespace_id=namespace.id,
        name="httpbin",
        base_url="https://httpbin.org",
        spec_source="openapi_url",
        openapi_url=HTTPBIN_SPEC_URL,
    )
    # Find /get but DO NOT enable it.
    endpoints = await svc.list_endpoints(namespace.id, "httpbin")
    disabled = next(e for e in endpoints if e.method == "GET" and e.path == "/get")
    assert disabled.enabled is False

    token = "bridge_" + uuid.uuid4().hex
    register_execution(
        token=token,
        namespace_id=namespace.id,
        namespace_name=namespace.name,
        execution_id=str(uuid.uuid4()),
    )
    try:
        from mcpworks_api.core.api_proxy import proxy_api_call

        ctx = resolve_execution(token)
        result = await proxy_api_call(ctx, "httpbin", disabled.operation_id, {}, {}, None, {}, db)
        assert result.error == "endpoint_disabled"
    finally:
        unregister_execution(token)


async def test_published_direct_tool_path(db, namespace):
    """T030/T034: publish an endpoint, then drive the direct-tool path (proxy_and_format)."""
    from mcpworks_api.core.api_proxy import (
        build_published_api_tool,
        parse_api_tool_name,
        proxy_and_format,
    )

    svc = ApiServerService(db)
    await svc.add_server(
        namespace_id=namespace.id,
        name="httpbin",
        base_url="https://httpbin.org",
        spec_source="openapi_url",
        openapi_url=HTTPBIN_SPEC_URL,
        auth=[
            {
                "name": "token",
                "location": "bearer",
                "format": "Bearer {value}",
                "source": "stored",
                "value": "published_TOKEN",
            }
        ],
    )
    # Find /bearer, enable + publish it, and build its direct-tool definition.
    endpoints = await svc.list_endpoints(namespace.id, "httpbin")
    bearer = next(e for e in endpoints if e.method == "GET" and e.path == "/bearer")
    await svc.set_enabled(namespace.id, "httpbin", [bearer.operation_id], enabled=True)
    await svc.set_published(namespace.id, "httpbin", bearer.operation_id, True)

    tool = build_published_api_tool(
        "httpbin",
        {
            "operation_id": bearer.operation_id,
            "method": bearer.method,
            "path": bearer.path,
            "summary": bearer.summary,
            "param_schema": bearer.param_schema,
            "request_body_schema": bearer.request_body_schema,
        },
    )
    server, op = parse_api_tool_name(tool["name"])
    assert (server, op) == ("httpbin", bearer.operation_id)

    token = "bridge_" + uuid.uuid4().hex
    register_execution(
        token=token,
        namespace_id=namespace.id,
        namespace_name=namespace.name,
        execution_id=str(uuid.uuid4()),
    )
    try:
        ctx = resolve_execution(token)
        ok, text = await proxy_and_format(
            ctx, server, op, {"path": {}, "query": {}, "headers": {}}, db, namespace=namespace
        )
        assert ok is True
        import json

        payload = json.loads(text)
        assert payload["status_code"] == 200
        # Stored bearer credential injected server-side and accepted by httpbin.
        assert payload["json"]["authenticated"] is True
        assert payload["json"]["token"] == "published_TOKEN"
    finally:
        unregister_execution(token)
