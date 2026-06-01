"""Integration tests for API → MCP service layer (feature 019).

Covers US1 (OpenAPI import + curation), US3 (manual endpoints), credential
storage/redaction (T032), and publish/unpublish (US4) at the service layer.

DB-only: uses an IP-literal public base_url (skips DNS) and inline `openapi_file`
specs (no network fetch), so these run against Postgres without internet.
Requires the test Postgres (see tests/conftest.py).
"""

import json
import uuid

import pytest

from mcpworks_api.core.exceptions import ConflictError, NotFoundError, ValidationError
from mcpworks_api.models import Account, Namespace, User
from mcpworks_api.services.api_server import ApiServerService

# Public IP literal → assert_url_allowed passes without a DNS lookup.
BASE_URL = "https://93.184.216.34"

ACME_SPEC = json.dumps(
    {
        "openapi": "3.0.3",
        "info": {"title": "Acme", "version": "1.0"},
        "paths": {
            "/orders": {
                "get": {
                    "operationId": "list_orders",
                    "summary": "List orders",
                    "parameters": [{"name": "status", "in": "query", "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/orders/{id}": {
                "get": {
                    "operationId": "get_order",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }
)


@pytest.fixture
async def namespace(db):
    user = User(
        email=f"api-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        name="API User",
        tier="free",
        status="active",
    )
    db.add(user)
    await db.flush()
    account = Account(user_id=user.id, name="Acct")
    db.add(account)
    await db.flush()
    ns = Namespace(account_id=account.id, name=f"ns-{uuid.uuid4().hex[:8]}")
    db.add(ns)
    await db.flush()
    return ns


async def test_openapi_file_import_and_curation(db, namespace):
    svc = ApiServerService(db)
    server, endpoints, dropped = await svc.add_server(
        namespace_id=namespace.id,
        name="acme",
        base_url=BASE_URL,
        spec_source="openapi_file",
        openapi_file=ACME_SPEC,
        enabled_endpoints=["list_orders"],
    )
    assert dropped == 0
    by_id = {e.operation_id: e for e in endpoints}
    assert set(by_id) == {"list_orders", "get_order"}
    # enabled_endpoints applied; the rest default disabled (curation).
    assert by_id["list_orders"].enabled is True
    assert by_id["get_order"].enabled is False
    assert server.endpoint_count == 2

    # list_endpoints filtering
    enabled = await svc.list_endpoints(namespace.id, "acme", filter_="enabled")
    assert [e.operation_id for e in enabled] == ["list_orders"]

    # enable the rest
    changed = await svc.set_enabled(namespace.id, "acme", ["get_order"], enabled=True)
    assert changed == ["get_order"]
    assert await svc._enabled_count(server.id) == 2


async def test_stored_credential_is_encrypted_and_redacted(db, namespace):
    svc = ApiServerService(db)
    server, _, _ = await svc.add_server(
        namespace_id=namespace.id,
        name="acme",
        base_url=BASE_URL,
        spec_source="manual",
        auth=[
            {
                "name": "api_key",
                "location": "header",
                "key": "X-API-Key",
                "format": "{value}",
                "source": "stored",
                "value": "sk_live_secret",
            }
        ],
    )
    # The auth JSONB definition must NOT contain the secret value.
    assert all("value" not in inj for inj in server.auth)
    assert server.credentials_encrypted is not None
    # The secret round-trips only via the internal decrypt helper.
    assert ApiServerService._decrypt_secrets(server) == {"api_key": "sk_live_secret"}

    # Rotate via set_credentials.
    await svc.set_credentials(namespace.id, "acme", "api_key", "sk_live_new")
    await db.refresh(server)
    assert ApiServerService._decrypt_secrets(server) == {"api_key": "sk_live_new"}


async def test_manual_endpoint_enabled_by_default(db, namespace):
    svc = ApiServerService(db)
    await svc.add_server(
        namespace_id=namespace.id, name="legacy", base_url=BASE_URL, spec_source="manual"
    )
    ep = await svc.add_manual_endpoint(
        namespace_id=namespace.id,
        name="legacy",
        operation_id="get_widget",
        method="GET",
        path="/v2/widgets/{id}",
        param_schema={"path": {"type": "object", "properties": {"id": {"type": "string"}}}},
    )
    assert ep.enabled is True
    assert ep.source == "manual"

    # Duplicate operation_id rejected.
    with pytest.raises(ConflictError):
        await svc.add_manual_endpoint(
            namespace_id=namespace.id,
            name="legacy",
            operation_id="get_widget",
            method="GET",
            path="/x",
        )
    # Invalid method rejected.
    with pytest.raises(ValidationError):
        await svc.add_manual_endpoint(
            namespace_id=namespace.id,
            name="legacy",
            operation_id="bad",
            method="FETCH",
            path="/x",
        )


async def test_publish_unpublish(db, namespace):
    svc = ApiServerService(db)
    await svc.add_server(
        namespace_id=namespace.id, name="acme", base_url=BASE_URL, spec_source="manual"
    )
    await svc.add_manual_endpoint(
        namespace_id=namespace.id, name="acme", operation_id="get_order", method="GET", path="/o"
    )
    ep = await svc.set_published(namespace.id, "acme", "get_order", True)
    assert ep.published is True
    published = await svc.list_endpoints(namespace.id, "acme", filter_="published")
    assert [e.operation_id for e in published] == ["get_order"]
    ep = await svc.set_published(namespace.id, "acme", "get_order", False)
    assert ep.published is False


async def test_remove_and_not_found(db, namespace):
    svc = ApiServerService(db)
    await svc.add_server(
        namespace_id=namespace.id, name="acme", base_url=BASE_URL, spec_source="manual"
    )
    await svc.add_manual_endpoint(
        namespace_id=namespace.id, name="acme", operation_id="op1", method="GET", path="/o"
    )
    n = await svc.remove_server(namespace.id, "acme")
    assert n == 1
    with pytest.raises(NotFoundError):
        await svc.get_by_name(namespace.id, "acme")


async def test_refresh_requires_openapi_source(db, namespace):
    svc = ApiServerService(db)
    await svc.add_server(
        namespace_id=namespace.id, name="manual-srv", base_url=BASE_URL, spec_source="manual"
    )
    with pytest.raises(ValidationError):
        await svc.refresh_endpoints(namespace.id, "manual-srv")
