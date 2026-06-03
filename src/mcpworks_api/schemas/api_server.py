"""Pydantic schemas for API → MCP management + internal proxy (feature 019).

Credential VALUES never appear in any response model — only injection
definitions (with values redacted) are surfaced.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Credential injections
# ---------------------------------------------------------------------------


class AuthInjectionIn(BaseModel):
    """A credential-injection definition supplied when adding a server.

    ``value`` is accepted only for ``source='stored'`` and is immediately
    encrypted + stripped; it is never echoed back. ``env_var`` is required for
    ``source='passthrough'``.
    """

    name: str
    location: Literal["header", "query", "bearer", "basic"]
    key: str | None = None
    format: str = "{value}"
    source: Literal["stored", "passthrough"]
    value: str | None = None  # stored only; write-only
    env_var: str | None = None  # passthrough only


class AuthInjectionOut(BaseModel):
    """Redacted injection definition for list/describe output."""

    name: str
    location: str
    key: str | None = None
    format: str = "{value}"
    source: str
    env_var: str | None = None
    value: str = "***redacted***"


# ---------------------------------------------------------------------------
# Endpoint summaries
# ---------------------------------------------------------------------------


class EndpointSummary(BaseModel):
    operation_id: str
    method: str
    path: str
    summary: str | None = None
    enabled: bool = False
    published: bool = False


# ---------------------------------------------------------------------------
# Management tool responses
# ---------------------------------------------------------------------------


class AddApiServerResponse(BaseModel):
    server: str
    spec_source: str
    endpoint_count: int
    enabled_count: int
    endpoints: list[EndpointSummary] = Field(default_factory=list)
    note: str | None = None


class ApiServerSummary(BaseModel):
    name: str
    base_url: str
    spec_source: str
    endpoint_count: int
    enabled_count: int
    enabled: bool
    last_refreshed_at: str | None = None


class ListApiServersResponse(BaseModel):
    servers: list[ApiServerSummary] = Field(default_factory=list)


class DescribeApiServerResponse(BaseModel):
    name: str
    base_url: str
    spec_source: str
    enabled: bool
    settings: dict = Field(default_factory=dict)
    auth: list[AuthInjectionOut] = Field(default_factory=list)
    endpoints: list[EndpointSummary] = Field(default_factory=list)
    last_refreshed_at: str | None = None


class ListEndpointsResponse(BaseModel):
    server: str
    endpoints: list[EndpointSummary] = Field(default_factory=list)


class RefreshEndpointsResponse(BaseModel):
    server: str
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    unchanged: int = 0
    preserved_enabled: list[str] = Field(default_factory=list)


class SettingsResponse(BaseModel):
    server: str
    settings: dict


class EndpointToggleResponse(BaseModel):
    server: str
    operation_ids: list[str] = Field(default_factory=list)
    now_enabled_count: int | None = None


class PublishResponse(BaseModel):
    server: str
    operation_id: str
    published: bool
    warning: str | None = None


class RemoveApiServerResponse(BaseModel):
    removed: str
    endpoints_removed: int


class ConfigureAgentApiResponse(BaseModel):
    agent: str
    api_server_names: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal proxy
# ---------------------------------------------------------------------------


class ApiProxyRequest(BaseModel):
    server: str
    operation_id: str
    path: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    body: Any | None = None
    headers: dict[str, str] = Field(default_factory=dict)
