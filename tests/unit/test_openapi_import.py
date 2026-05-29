"""Unit tests for the OpenAPI/Swagger importer (feature 019, T020)."""

from pathlib import Path

import pytest

from mcpworks_api.core.openapi_import import (
    OpenAPIImportError,
    extract_endpoints,
    parse_spec,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "openapi_samples"


def _load(name: str) -> dict:
    return parse_spec((FIXTURES / name).read_text())


def test_openapi_3_0_basic() -> None:
    result = extract_endpoints(_load("acme_3_0.json"))
    by_id = {e.operation_id: e for e in result.endpoints}
    assert set(by_id) == {"list_orders", "create_order", "get_order"}
    assert result.total_discovered == 3
    assert result.truncated is False

    # Path param bucketed correctly.
    get_order = by_id["get_order"]
    assert get_order.method == "GET"
    assert get_order.param_schema["path"]["properties"]["id"]["type"] == "string"
    assert get_order.param_schema["path"]["required"] == ["id"]

    # Query params bucketed.
    list_orders = by_id["list_orders"]
    assert set(list_orders.param_schema["query"]["properties"]) == {"status", "limit"}

    # POST body extracted.
    create = by_id["create_order"]
    assert create.method == "POST"
    assert create.request_body_schema["properties"]["sku"]["type"] == "string"


def test_openapi_3_1_ref_resolution_and_shared_params() -> None:
    result = extract_endpoints(_load("widgets_3_1_ref.json"))
    by_id = {e.operation_id: e for e in result.endpoints}
    assert set(by_id) == {"get_widget", "replace_widget"}

    # Path-level shared param applies to both operations.
    assert "id" in by_id["get_widget"].param_schema["path"]["properties"]
    assert "id" in by_id["replace_widget"].param_schema["path"]["properties"]

    # $ref resolved into the body schema (PUT is idempotent so body is allowed).
    body = by_id["replace_widget"].request_body_schema
    assert body["type"] == "object"
    assert "color" in body["properties"]


def test_swagger_2_0_operation_id_derivation_and_body() -> None:
    result = extract_endpoints(_load("legacy_swagger_2_0.yaml"))
    ids = {e.operation_id for e in result.endpoints}
    # No operationId in spec → derived as {method}_{slug(path)}.
    assert ids == {"get_things", "post_things"}

    by_id = {e.operation_id: e for e in result.endpoints}
    # Swagger 2.0 non-body param.
    assert by_id["get_things"].param_schema["query"]["properties"]["q"]["type"] == "string"
    # Swagger 2.0 in:body parameter → request_body_schema.
    post = by_id["post_things"]
    assert post.request_body_schema["properties"]["label"]["type"] == "string"


def test_operation_id_collision_suffix() -> None:
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/a": {"get": {"operationId": "dup", "responses": {}}},
            "/b": {"get": {"operationId": "dup", "responses": {}}},
        },
    }
    result = extract_endpoints(spec)
    ids = sorted(e.operation_id for e in result.endpoints)
    assert ids == ["dup", "dup_2"]


def test_ceiling_truncation() -> None:
    paths = {f"/p{i}": {"get": {"operationId": f"op{i}", "responses": {}}} for i in range(10)}
    spec = {"openapi": "3.0.0", "paths": paths}
    result = extract_endpoints(spec, ceiling=4)
    assert len(result.endpoints) == 4
    assert result.total_discovered == 10
    assert result.truncated is True


def test_no_paths_raises() -> None:
    with pytest.raises(OpenAPIImportError):
        extract_endpoints({"openapi": "3.0.0"})


def test_parse_spec_rejects_garbage() -> None:
    with pytest.raises(OpenAPIImportError):
        parse_spec("")
