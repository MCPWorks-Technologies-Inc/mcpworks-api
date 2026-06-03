"""API proxy core — routes sandbox calls to a registered REST API (feature 019).

Bridge key → execution context → namespace → resolve server+endpoint →
inject credentials server-side → SSRF gate → upstream HTTP call.

Credential values (stored or passthrough) are injected here and never cross the
sandbox boundary. POST/PATCH are never auto-retried (idempotency safety).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.encryption import decrypt_value
from mcpworks_api.core.exec_token_registry import ExecutionContext
from mcpworks_api.core.ssrf import SSRFError, assert_url_allowed
from mcpworks_api.models.api_endpoint import ApiEndpoint
from mcpworks_api.models.namespace_api_server import (
    DEFAULT_SETTINGS,
    IDEMPOTENT_METHODS,
    NamespaceApiServer,
)

logger = structlog.get_logger(__name__)

# Transient gateway statuses worth retrying on idempotent methods (flaky upstreams).
_RETRYABLE_STATUSES = frozenset({502, 503, 504})


@dataclass
class ApiProxyResult:
    status_code: int | None = None
    json_body: Any = None
    text: str | None = None
    content_type: str | None = None
    truncated: bool = False
    error: str | None = None
    error_type: str | None = None
    reason: str | None = None
    action: str | None = None


def _err(error: str, reason: str, action: str) -> ApiProxyResult:
    return ApiProxyResult(error=error, error_type=error, reason=reason, action=action)


def _build_path(path_template: str, path_args: dict[str, Any]) -> str:
    """Substitute {param} placeholders in a path template."""

    def repl(match: Any) -> str:
        key = match.group(1)
        if key not in path_args:
            raise KeyError(key)
        return str(path_args[key])

    import re

    return re.sub(r"\{([^}]+)\}", repl, path_template)


def _apply_injections(
    auth: list[dict[str, Any]],
    secrets: dict[str, str],
    passthrough_env: dict[str, str],
    headers: dict[str, str],
    query: dict[str, Any],
) -> str | None:
    """Inject each credential into headers/query. Returns an error code or None."""
    for inj in auth:
        source = inj.get("source")
        if source == "stored":
            raw = secrets.get(inj["name"])
        else:  # passthrough — resolved server-side from execution env only
            env_var = inj.get("env_var")
            raw = passthrough_env.get(env_var) if env_var else None
        if raw is None:
            return str(inj.get("name", "credential"))
        value = inj.get("format", "{value}").replace("{value}", raw)
        location = inj["location"]
        if location == "bearer":
            headers["Authorization"] = (
                value if value.lower().startswith("bearer ") else f"Bearer {value}"
            )
        elif location == "basic":
            headers["Authorization"] = (
                value if value.lower().startswith("basic ") else f"Basic {value}"
            )
        elif location == "header":
            headers[inj.get("key") or inj["name"]] = value
        elif location == "query":
            query[inj.get("key") or inj["name"]] = value
    return None


async def proxy_api_call(
    ctx: ExecutionContext,
    server_name: str,
    operation_id: str,
    path: dict[str, Any],
    query: dict[str, Any],
    body: Any,
    headers: dict[str, str],
    db: AsyncSession,
) -> ApiProxyResult:
    start = time.monotonic()

    server = (
        await db.execute(
            select(NamespaceApiServer).where(
                NamespaceApiServer.namespace_id == ctx.namespace_id,
                NamespaceApiServer.name == server_name,
            )
        )
    ).scalar_one_or_none()
    if not server:
        return _err("endpoint_not_found", f"API server '{server_name}' not found", "check name")
    if not server.enabled:
        return _err("endpoint_disabled", f"API server '{server_name}' is disabled", "enable it")

    endpoint = (
        await db.execute(
            select(ApiEndpoint).where(
                ApiEndpoint.api_server_id == server.id,
                ApiEndpoint.operation_id == operation_id,
            )
        )
    ).scalar_one_or_none()
    if not endpoint:
        return _err(
            "endpoint_not_found",
            f"endpoint '{operation_id}' not found on '{server_name}'",
            "list_endpoints to see available operations",
        )
    if not (endpoint.enabled or endpoint.published):
        return _err(
            "endpoint_disabled",
            f"endpoint '{operation_id}' is disabled",
            "enable_endpoint before calling it",
        )

    settings = {**DEFAULT_SETTINGS, **(server.settings or {})}
    max_calls = settings.get("max_calls_per_execution", 50)
    if ctx.api_calls_count >= max_calls:
        return _err(
            "max_calls_exceeded",
            f"exceeded {max_calls} API calls for this execution",
            "reduce calls or raise max_calls_per_execution",
        )

    # Build request components.
    req_headers: dict[str, str] = {}
    if server.default_headers_encrypted and server.default_headers_dek_encrypted:
        try:
            req_headers.update(
                decrypt_value(
                    server.default_headers_encrypted, server.default_headers_dek_encrypted
                )
            )
        except Exception:
            return _err("upstream_error", "failed to decrypt default headers", "re-add the server")
    req_headers.update(headers or {})
    req_query = dict(query or {})

    secrets: dict[str, str] = {}
    if server.credentials_encrypted and server.credentials_dek_encrypted:
        try:
            secrets = dict(
                decrypt_value(server.credentials_encrypted, server.credentials_dek_encrypted)
            )
        except Exception:
            return _err("upstream_error", "failed to decrypt credentials", "re-set credentials")

    missing = _apply_injections(
        server.auth or [], secrets, ctx.passthrough_env, req_headers, req_query
    )
    if missing:
        env_var = next((a.get("env_var") for a in server.auth if a.get("name") == missing), None)
        return _err(
            "missing_credential",
            f"credential '{missing}' unavailable",
            f"set {env_var} in execution env" if env_var else f"set credential '{missing}'",
        )

    try:
        rel_path = _build_path(endpoint.path, path or {})
    except KeyError as e:
        return _err("upstream_error", f"missing path parameter {e}", "provide all path params")

    url = server.base_url.rstrip("/") + "/" + rel_path.lstrip("/")

    try:
        await assert_url_allowed(url)
    except SSRFError as e:
        latency = int((time.monotonic() - start) * 1000)
        _record(ctx, server_name, operation_id, endpoint.method, latency, 0, None, "ssrf_blocked")
        return _err("ssrf_blocked", str(e), "use a public API host")

    method = endpoint.method.upper()
    timeout = settings.get("timeout_seconds", 30)
    retry = settings.get("retry_on_failure", True) and method in IDEMPOTENT_METHODS
    attempts = 1 + (settings.get("retry_count", 2) if retry else 0)
    response_limit = settings.get("response_limit_bytes", 1048576)

    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
                resp = await client.request(
                    method,
                    url,
                    params=req_query or None,
                    headers=req_headers or None,
                    json=body if body is not None else None,
                )
            # Retry transient gateway errors on idempotent methods (e.g. a flaky upstream
            # returning 502/503/504). Non-idempotent methods never reach here (retry=False).
            if retry and resp.status_code in _RETRYABLE_STATUSES and attempt < attempts - 1:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            ctx.api_calls_count += 1
            latency = int((time.monotonic() - start) * 1000)
            raw = resp.content
            truncated = len(raw) > response_limit
            content_type = resp.headers.get("content-type", "")
            result = ApiProxyResult(
                status_code=resp.status_code,
                content_type=content_type,
                truncated=truncated,
            )
            if "application/json" in content_type and not truncated:
                try:
                    result.json_body = resp.json()
                except ValueError:
                    result.text = resp.text[:response_limit]
            else:
                result.text = raw[:response_limit].decode("utf-8", errors="replace")
            _record(
                ctx,
                server_name,
                operation_id,
                method,
                latency,
                len(raw),
                resp.status_code,
                None,
                truncated,
            )
            return result
        except httpx.TimeoutException as e:
            last_exc = e
            if attempt >= attempts - 1:
                latency = int((time.monotonic() - start) * 1000)
                _record(ctx, server_name, operation_id, method, latency, 0, None, "timeout")
                return _err(
                    "timeout", f"upstream timed out after {timeout}s", "increase timeout_seconds"
                )
        except httpx.HTTPError as e:
            last_exc = e
            if attempt < attempts - 1:
                await asyncio.sleep(0.5 * (2**attempt))

    latency = int((time.monotonic() - start) * 1000)
    _record(ctx, server_name, operation_id, method, latency, 0, None, "upstream_error")
    return _err("upstream_error", f"request failed: {str(last_exc)[:200]}", "check the API host")


def build_published_api_tool(server_name: str, endpoint: dict[str, Any]) -> dict[str, Any]:
    """Build an MCPTool-compatible dict for a published API endpoint (019, T030/T033).

    Exposes an endpoint as a DIRECT MCP tool (raw response) to code-mode clients and
    to agents. Server names are DNS-safe (no underscores), so the
    ``api__{server}__{operation_id}`` name round-trips unambiguously via
    ``parse_api_tool_name``. The tool args mirror the proxy request shape. Returns the
    MCP ``inputSchema`` key; agent callers rename it to ``input_schema``.
    """
    op = endpoint["operation_id"]
    method = endpoint.get("method", "GET")
    path = endpoint.get("path", "")
    summary = endpoint.get("summary") or f"{method} {path}"
    param_schema = endpoint.get("param_schema") or {}
    props: dict[str, Any] = {
        "path": param_schema.get("path") or {"type": "object"},
        "query": param_schema.get("query") or {"type": "object"},
        "headers": param_schema.get("header") or {"type": "object"},
    }
    if endpoint.get("request_body_schema"):
        props["body"] = endpoint["request_body_schema"]
    return {
        "name": f"api__{server_name}__{op}",
        "description": f"{method} {path} — {summary} [raw API response; published endpoint]",
        "inputSchema": {"type": "object", "properties": props},
    }


def parse_api_tool_name(name: str) -> tuple[str, str] | None:
    """Parse ``api__{server}__{operation_id}`` → (server, operation_id), or None.

    Server names contain no underscores (DNS-safe), so the first ``__`` after the
    ``api__`` prefix is the server/operation boundary.
    """
    if not name.startswith("api__"):
        return None
    rest = name[len("api__") :]
    if "__" not in rest:
        return None
    server, operation_id = rest.split("__", 1)
    if not server or not operation_id:
        return None
    return server, operation_id


async def _scan_response(
    text: str,
    namespace: Any,
    server_name: str,
    operation_id: str,
    execution_id: str,
) -> str:
    """Run a direct-tool API response through the namespace scanner pipeline (019, T034).

    Only the direct-tool path (published endpoints / agent tools) calls this — the
    functions-only path's data is scanned later at function-output time. No-op when
    the namespace has no scanner pipeline configured.
    """
    pipeline_config = getattr(namespace, "scanner_pipeline", None)
    if not pipeline_config:
        return text
    try:
        from mcpworks_api.core.scanner_pipeline import evaluate_pipeline
        from mcpworks_api.core.scanners.base import ScanContext

        result = await evaluate_pipeline(
            text,
            ScanContext(
                direction="output",
                namespace=getattr(namespace, "name", ""),
                service=f"api:{server_name}",
                function=operation_id,
                execution_id=execution_id,
                output_trust="prompt",
            ),
            pipeline_config,
        )
        if result.final_action == "block":
            return json.dumps(
                {"error": "blocked_by_scanner", "reason": "response blocked by injection scanner"}
            )
        if result.modified_content is not None:
            return result.modified_content
    except Exception:
        logger.debug("api_response_scan_failed", server=server_name, op=operation_id)
    return text


async def proxy_and_format(
    ctx: ExecutionContext,
    server_name: str,
    operation_id: str,
    arguments: dict[str, Any],
    db: AsyncSession,
    *,
    namespace: Any = None,
    execution_id: str = "",
) -> tuple[bool, str]:
    """Direct-tool entry point: proxy a published endpoint and return (ok, json_text).

    Used by the run handler (published tools) and the agent orchestrator. Builds the
    proxy request from the tool ``arguments`` (path/query/body/headers), formats the
    response envelope, and scans it (T034) before returning to the AI.
    """
    result = await proxy_api_call(
        ctx,
        server_name,
        operation_id,
        arguments.get("path") or {},
        arguments.get("query") or {},
        arguments.get("body"),
        arguments.get("headers") or {},
        db,
    )
    if result.error:
        return False, json.dumps(
            {"error": result.error, "reason": result.reason, "action": result.action}
        )
    payload: dict[str, Any] = {
        "status_code": result.status_code,
        "truncated": result.truncated,
        "content_type": result.content_type,
    }
    if result.json_body is not None:
        payload["json"] = result.json_body
    if result.text is not None:
        payload["text"] = result.text
    text = json.dumps(payload)
    if namespace is not None:
        text = await _scan_response(text, namespace, server_name, operation_id, execution_id)
    return True, text


def _record(
    ctx: ExecutionContext,
    server_name: str,
    operation_id: str,
    method: str,
    latency_ms: int,
    response_bytes: int,
    status_code: int | None,
    error_type: str | None,
    truncated: bool = False,
) -> None:
    from mcpworks_api.services import analytics

    asyncio.create_task(
        analytics.record_api_proxy_call(
            namespace_id=ctx.namespace_id,
            api_server=server_name,
            operation_id=operation_id,
            method=method,
            latency_ms=latency_ms,
            response_bytes=response_bytes,
            status_code=status_code,
            error_type=error_type,
            truncated=truncated,
        )
    )
