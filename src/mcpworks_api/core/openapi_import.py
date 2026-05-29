"""Minimal OpenAPI / Swagger extractor for API → MCP (feature 019).

Deliberately in-house (research R1): no heavy dependency, reuses PyYAML + the
standard library. Extracts just enough structure to (a) list endpoints for the
LLM to curate and (b) let the proxy build an upstream request. Supports
OpenAPI 3.0/3.1 and Swagger 2.0. Local ``$ref`` only (research R3) — remote refs
are an SSRF/reliability hazard and are left unresolved (permissive fallback).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from mcpworks_api.models.namespace_api_server import MAX_ENDPOINTS_PER_SERVER

HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
_MAX_REF_DEPTH = 32


class OpenAPIImportError(Exception):
    """Raised when a spec cannot be parsed or contains no usable paths."""


@dataclass
class ImportedEndpoint:
    operation_id: str
    method: str
    path: str
    summary: str | None = None
    param_schema: dict[str, Any] = field(default_factory=dict)
    request_body_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "method": self.method,
            "path": self.path,
            "summary": self.summary,
            "param_schema": self.param_schema,
            "request_body_schema": self.request_body_schema,
            "response_schema": self.response_schema,
        }


@dataclass
class ImportResult:
    endpoints: list[ImportedEndpoint]
    total_discovered: int
    truncated: bool


def parse_spec(text: str) -> dict[str, Any]:
    """Parse a spec document (JSON or YAML) into a dict. Format detected by content."""
    text = text.strip()
    if not text:
        raise OpenAPIImportError("empty spec document")
    # Try JSON first (fast path), then YAML.
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        try:
            import yaml

            doc = yaml.safe_load(text)
        except Exception as e:  # noqa: BLE001
            raise OpenAPIImportError(f"could not parse spec as JSON or YAML: {e}") from e
    if not isinstance(doc, dict):
        raise OpenAPIImportError("spec document is not a mapping")
    return doc


def _slug(text: str) -> str:
    """Lowercase, identifier-safe slug for an operation_id handle."""
    s = re.sub(r"[^a-z0-9_]+", "_", text.lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "op"


def _derive_operation_id(method: str, path: str) -> str:
    """Fallback handle when the spec omits operationId: {method}_{slug(path)}."""
    return _slug(f"{method}_{path}")


def _resolve_ref(ref: str, root: dict[str, Any]) -> Any:
    """Resolve a local ``#/a/b/c`` JSON pointer against the root document."""
    if not ref.startswith("#/"):
        return None  # remote ref — not resolved (research R3)
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def _deref(node: Any, root: dict[str, Any], depth: int = 0) -> Any:
    """Recursively resolve local $refs. Unresolvable refs degrade to ``{}``."""
    if depth > _MAX_REF_DEPTH:
        return {}
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str):
            resolved = _resolve_ref(node["$ref"], root)
            if resolved is None:
                return {}
            return _deref(resolved, root, depth + 1)
        return {k: _deref(v, root, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [_deref(item, root, depth + 1) for item in node]
    return node


def _swagger2_param_property(param: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-schema property fragment for a Swagger 2.0 non-body parameter."""
    prop: dict[str, Any] = {}
    for key in ("type", "format", "items", "enum", "description", "default"):
        if key in param:
            prop[key] = param[key]
    return prop or {"type": "string"}


def _bucket_parameters(
    parameters: list[dict[str, Any]],
    root: dict[str, Any],
    *,
    is_swagger2: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Sort parameters into {path, query, header} buckets + optional body schema."""
    buckets: dict[str, dict[str, Any]] = {
        "path": {"type": "object", "properties": {}, "required": []},
        "query": {"type": "object", "properties": {}, "required": []},
        "header": {"type": "object", "properties": {}, "required": []},
    }
    body_schema: dict[str, Any] | None = None

    for raw in parameters:
        param = _deref(raw, root)
        if not isinstance(param, dict):
            continue
        location = param.get("in")
        name = param.get("name")
        if location == "body":  # Swagger 2.0 body parameter
            body_schema = param.get("schema", {})
            continue
        if location not in ("path", "query", "header") or not name:
            continue
        if is_swagger2:
            prop = _swagger2_param_property(param)
        else:
            prop = param.get("schema", {"type": "string"})
        buckets[location]["properties"][name] = prop
        if param.get("required"):
            buckets[location]["required"].append(name)

    # Drop empty required lists for cleanliness.
    for b in buckets.values():
        if not b["required"]:
            b.pop("required")
    return buckets, body_schema


def _extract_request_body(operation: dict[str, Any]) -> dict[str, Any] | None:
    """OpenAPI 3.x requestBody → JSON schema (prefers application/json)."""
    rb = operation.get("requestBody")
    if not isinstance(rb, dict):
        return None
    content = rb.get("content", {})
    if not isinstance(content, dict):
        return None
    for mime in ("application/json", *content.keys()):
        media = content.get(mime)
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            return media["schema"]  # type: ignore[no-any-return]
    return None


def _extract_response_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort 2xx response schema (informational)."""
    responses = operation.get("responses", {})
    if not isinstance(responses, dict):
        return None
    for code in ("200", "201", "2XX", "default", *responses.keys()):
        resp = responses.get(code)
        if not isinstance(resp, dict):
            continue
        if isinstance(resp.get("schema"), dict):  # Swagger 2.0
            return resp["schema"]  # type: ignore[no-any-return]
        content = resp.get("content")  # OpenAPI 3.x
        if isinstance(content, dict):
            for media in content.values():
                if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                    return media["schema"]  # type: ignore[no-any-return]
    return None


def extract_endpoints(
    spec: dict[str, Any],
    *,
    ceiling: int = MAX_ENDPOINTS_PER_SERVER,
) -> ImportResult:
    """Extract endpoints from a parsed OpenAPI/Swagger document.

    Returns endpoints (capped at ``ceiling``), the total discovered count, and a
    truncated flag. ``operation_id`` is the spec's slugged operationId, else
    ``{method}_{slug(path)}``, with deterministic ``_N`` suffixes on collision.
    """
    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise OpenAPIImportError("spec has no 'paths'")

    is_swagger2 = str(spec.get("swagger", "")).startswith("2")

    endpoints: list[ImportedEndpoint] = []
    seen_ids: set[str] = set()
    total = 0

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        # Path-level parameters apply to every operation under the path.
        shared_params = path_item.get("parameters", []) or []
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            total += 1
            if len(endpoints) >= ceiling:
                continue  # keep counting total, but stop materializing

            raw_op_id = operation.get("operationId")
            op_id = _slug(raw_op_id) if raw_op_id else _derive_operation_id(method, path)
            # Deterministic collision suffix.
            candidate = op_id
            n = 2
            while candidate in seen_ids:
                candidate = f"{op_id}_{n}"
                n += 1
            seen_ids.add(candidate)

            all_params = list(shared_params) + list(operation.get("parameters", []) or [])
            param_schema, swagger_body = _bucket_parameters(
                all_params, spec, is_swagger2=is_swagger2
            )
            request_body = swagger_body if is_swagger2 else _extract_request_body(operation)

            endpoints.append(
                ImportedEndpoint(
                    operation_id=candidate,
                    method=method.upper(),
                    path=path,
                    summary=(operation.get("summary") or operation.get("description") or None),
                    param_schema=param_schema,
                    request_body_schema=_deref(request_body, spec) if request_body else None,
                    response_schema=_extract_response_schema(operation),
                )
            )

    if total == 0:
        raise OpenAPIImportError("spec 'paths' contains no operations")

    return ImportResult(
        endpoints=endpoints,
        total_discovered=total,
        truncated=total > len(endpoints),
    )
