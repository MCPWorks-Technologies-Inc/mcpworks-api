"""API server registry service — register REST APIs as ad-hoc MCPs (feature 019).

Handles server CRUD, OpenAPI/manual endpoint discovery, LLM curation
(enable/disable), stored-credential encryption, and raw-endpoint publishing.
Credential VALUES live only in the encrypted column; the ``auth`` JSONB holds
definitions only, so redaction is structural.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.encryption import decrypt_value, encrypt_value
from mcpworks_api.core.exceptions import ConflictError, NotFoundError, ValidationError
from mcpworks_api.core.openapi_import import OpenAPIImportError, extract_endpoints, parse_spec
from mcpworks_api.core.ssrf import SSRFError, assert_url_allowed
from mcpworks_api.models.api_endpoint import ApiEndpoint
from mcpworks_api.models.namespace_api_server import (
    DEFAULT_SETTINGS,
    VALID_SPEC_SOURCES,
    NamespaceApiServer,
)

logger = structlog.get_logger(__name__)

MAX_SERVERS_PER_NAMESPACE = 20

VALID_SETTINGS_KEYS: dict[str, type] = {
    "response_limit_bytes": int,
    "timeout_seconds": int,
    "max_calls_per_execution": int,
    "retry_on_failure": bool,
    "retry_count": int,
    "enabled": bool,
}

VALID_LOCATIONS = frozenset({"header", "query", "bearer", "basic"})
VALID_SOURCES = frozenset({"stored", "passthrough"})
VALID_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})

_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_OPID_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,127}$")


class ApiServerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _split_auth(auth: list[dict[str, Any]] | None) -> tuple[list[dict], dict[str, str]]:
        """Split incoming auth into (definitions-without-values, name→secret map).

        Validates each injection. Stored injections must carry ``value``;
        passthrough injections must carry ``env_var`` and never a value.
        """
        definitions: list[dict] = []
        secrets: dict[str, str] = {}
        for raw in auth or []:
            name = raw.get("name")
            location = raw.get("location")
            source = raw.get("source")
            if not name or location not in VALID_LOCATIONS or source not in VALID_SOURCES:
                raise ValidationError(f"invalid auth injection: {raw!r}")
            definition = {
                "name": name,
                "location": location,
                "key": raw.get("key"),
                "format": raw.get("format", "{value}"),
                "source": source,
            }
            if source == "stored":
                value = raw.get("value")
                if not value:
                    raise ValidationError(f"stored injection '{name}' requires a value")
                secrets[name] = value
            else:  # passthrough
                env_var = raw.get("env_var")
                if not env_var:
                    raise ValidationError(f"passthrough injection '{name}' requires env_var")
                definition["env_var"] = env_var
            definitions.append(definition)
        return definitions, secrets

    async def _get_optional(self, namespace_id: uuid.UUID, name: str) -> NamespaceApiServer | None:
        stmt = select(NamespaceApiServer).where(
            NamespaceApiServer.namespace_id == namespace_id,
            NamespaceApiServer.name == name,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_name(self, namespace_id: uuid.UUID, name: str) -> NamespaceApiServer:
        server = await self._get_optional(namespace_id, name)
        if not server:
            raise NotFoundError(f"API server '{name}' not found")
        return server

    async def _endpoints(self, server_id: uuid.UUID) -> list[ApiEndpoint]:
        stmt = (
            select(ApiEndpoint)
            .where(ApiEndpoint.api_server_id == server_id)
            .order_by(ApiEndpoint.operation_id)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def _enabled_count(self, server_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            ApiEndpoint.api_server_id == server_id, ApiEndpoint.enabled.is_(True)
        )
        return int((await self.db.execute(stmt)).scalar_one())

    # ------------------------------------------------------------------ add

    async def add_server(
        self,
        namespace_id: uuid.UUID,
        name: str,
        base_url: str,
        spec_source: str = "manual",
        openapi_url: str | None = None,
        openapi_file: str | None = None,
        auth: list[dict[str, Any]] | None = None,
        description: str | None = None,
        default_headers: dict[str, str] | None = None,
        settings: dict[str, Any] | None = None,
        enabled_endpoints: list[str] | None = None,
    ) -> tuple[NamespaceApiServer, list[ApiEndpoint]]:
        if not _NAME_RE.match(name):
            raise ValidationError(f"invalid server name '{name}' (must be DNS-safe)")
        if spec_source not in VALID_SPEC_SOURCES:
            raise ValidationError(f"invalid spec_source '{spec_source}'")
        if await self._get_optional(namespace_id, name):
            raise ConflictError(f"API server '{name}' already exists in this namespace")

        count = (
            await self.db.execute(
                select(func.count()).where(NamespaceApiServer.namespace_id == namespace_id)
            )
        ).scalar_one()
        if count >= MAX_SERVERS_PER_NAMESPACE:
            raise ValidationError(
                f"namespace already has the maximum of {MAX_SERVERS_PER_NAMESPACE} API servers"
            )

        try:
            await assert_url_allowed(base_url)
        except SSRFError as e:
            raise ValidationError(f"base_url rejected: {e}") from e

        definitions, secrets = self._split_auth(auth)

        creds_enc = creds_dek = None
        if secrets:
            creds_enc, creds_dek = encrypt_value(secrets)
        headers_enc = headers_dek = None
        if default_headers:
            headers_enc, headers_dek = encrypt_value(default_headers)

        server = NamespaceApiServer(
            namespace_id=namespace_id,
            name=name,
            description=description,
            base_url=base_url.rstrip("/"),
            spec_source=spec_source,
            openapi_url=openapi_url,
            auth=definitions,
            credentials_encrypted=creds_enc,
            credentials_dek_encrypted=creds_dek,
            default_headers_encrypted=headers_enc,
            default_headers_dek_encrypted=headers_dek,
            settings=settings or {},
        )
        self.db.add(server)
        await self.db.flush()

        endpoints: list[ApiEndpoint] = []
        if spec_source in ("openapi_url", "openapi_file"):
            endpoints = await self._import_openapi(
                server, openapi_url=openapi_url, openapi_file=openapi_file
            )
            enable_set = set(enabled_endpoints or [])
            for ep in endpoints:
                if ep.operation_id in enable_set:
                    ep.enabled = True
            server.endpoint_count = len(endpoints)
            server.last_refreshed_at = datetime.now(UTC)

        await self.db.flush()
        await self.db.refresh(server)
        return server, endpoints

    async def _fetch_spec_text(self, openapi_url: str) -> str:
        import httpx

        try:
            await assert_url_allowed(openapi_url)
        except SSRFError as e:
            raise ValidationError(f"openapi_url rejected: {e}") from e
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=15) as client:
                resp = await client.get(openapi_url)
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPError as e:
            raise ValidationError(f"could not fetch OpenAPI spec: {e}") from e

    async def _import_openapi(
        self,
        server: NamespaceApiServer,
        *,
        openapi_url: str | None,
        openapi_file: str | None,
    ) -> list[ApiEndpoint]:
        if openapi_url:
            text = await self._fetch_spec_text(openapi_url)
        elif openapi_file:
            text = openapi_file
        else:
            raise ValidationError("openapi spec_source requires openapi_url or openapi_file")

        try:
            spec = parse_spec(text)
            result = extract_endpoints(spec)
        except OpenAPIImportError as e:
            raise ValidationError(f"OpenAPI import failed: {e}") from e

        endpoints: list[ApiEndpoint] = []
        for imported in result.endpoints:
            ep = ApiEndpoint(
                api_server_id=server.id,
                operation_id=imported.operation_id,
                method=imported.method,
                path=imported.path,
                summary=imported.summary,
                param_schema=imported.param_schema,
                request_body_schema=imported.request_body_schema,
                response_schema=imported.response_schema,
                enabled=False,
                source="imported",
            )
            self.db.add(ep)
            endpoints.append(ep)
        await self.db.flush()
        return endpoints

    # ------------------------------------------------------------------ refresh

    async def refresh_endpoints(
        self, namespace_id: uuid.UUID, name: str
    ) -> tuple[list[str], list[str], list[str], int, list[str]]:
        """Re-import OpenAPI, preserving enabled/published by operation_id.

        Returns (added, removed, changed, unchanged, preserved_enabled).
        """
        server = await self.get_by_name(namespace_id, name)
        if server.spec_source not in ("openapi_url", "openapi_file") or not server.openapi_url:
            raise ValidationError(f"server '{name}' has no OpenAPI source to refresh")

        existing = {ep.operation_id: ep for ep in await self._endpoints(server.id)}
        # Manual endpoints are untouched by refresh.
        manual_ids = {oid for oid, ep in existing.items() if ep.source == "manual"}

        text = await self._fetch_spec_text(server.openapi_url)
        try:
            result = extract_endpoints(parse_spec(text))
        except OpenAPIImportError as e:
            raise ValidationError(f"OpenAPI refresh failed (cached endpoints kept): {e}") from e

        incoming = {e.operation_id: e for e in result.endpoints}
        added, changed, preserved = [], [], []
        for oid, imp in incoming.items():
            if oid in existing and existing[oid].source == "imported":
                ep = existing[oid]
                if (ep.method, ep.path) != (imp.method, imp.path) or (
                    ep.param_schema != imp.param_schema
                ):
                    changed.append(oid)
                ep.method, ep.path, ep.summary = imp.method, imp.path, imp.summary
                ep.param_schema = imp.param_schema
                ep.request_body_schema = imp.request_body_schema
                ep.response_schema = imp.response_schema
                if ep.enabled:
                    preserved.append(oid)
            elif oid not in existing:
                self.db.add(
                    ApiEndpoint(
                        api_server_id=server.id,
                        operation_id=oid,
                        method=imp.method,
                        path=imp.path,
                        summary=imp.summary,
                        param_schema=imp.param_schema,
                        request_body_schema=imp.request_body_schema,
                        response_schema=imp.response_schema,
                        enabled=False,
                        source="imported",
                    )
                )
                added.append(oid)

        removed = []
        for oid, ep in existing.items():
            if ep.source == "imported" and oid not in incoming:
                await self.db.delete(ep)
                removed.append(oid)

        unchanged = len(incoming) - len(added) - len(changed)
        server.endpoint_count = len(incoming) + len(manual_ids - set(incoming))
        server.last_refreshed_at = datetime.now(UTC)
        await self.db.flush()
        return added, removed, changed, max(unchanged, 0), preserved

    # ------------------------------------------------------------------ CRUD

    async def list_servers(self, namespace_id: uuid.UUID) -> list[NamespaceApiServer]:
        stmt = (
            select(NamespaceApiServer)
            .where(NamespaceApiServer.namespace_id == namespace_id)
            .order_by(NamespaceApiServer.name)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def remove_server(self, namespace_id: uuid.UUID, name: str) -> int:
        server = await self.get_by_name(namespace_id, name)
        n = len(await self._endpoints(server.id))
        await self.db.delete(server)
        await self.db.flush()
        return n

    async def update_settings(
        self, namespace_id: uuid.UUID, name: str, updates: dict[str, Any]
    ) -> dict:
        server = await self.get_by_name(namespace_id, name)
        for key, value in updates.items():
            if key not in VALID_SETTINGS_KEYS:
                raise ValidationError(f"unknown setting '{key}'")
            if not isinstance(value, VALID_SETTINGS_KEYS[key]):
                raise ValidationError(
                    f"setting '{key}' must be {VALID_SETTINGS_KEYS[key].__name__}"
                )
            if key == "enabled":
                server.enabled = bool(value)
            else:
                server.settings = {**(server.settings or {}), key: value}
        await self.db.flush()
        await self.db.refresh(server)
        return {**DEFAULT_SETTINGS, **(server.settings or {}), "enabled": server.enabled}

    async def set_credentials(
        self, namespace_id: uuid.UUID, name: str, injection_name: str, value: str
    ) -> None:
        server = await self.get_by_name(namespace_id, name)
        definition = next((a for a in server.auth if a.get("name") == injection_name), None)
        if not definition:
            raise NotFoundError(f"injection '{injection_name}' not found on server '{name}'")
        if definition.get("source") != "stored":
            raise ValidationError(f"injection '{injection_name}' is not a stored credential")
        secrets = self._decrypt_secrets(server)
        secrets[injection_name] = value
        server.credentials_encrypted, server.credentials_dek_encrypted = encrypt_value(secrets)
        await self.db.flush()

    @staticmethod
    def _decrypt_secrets(server: NamespaceApiServer) -> dict[str, str]:
        if not (server.credentials_encrypted and server.credentials_dek_encrypted):
            return {}
        return dict(decrypt_value(server.credentials_encrypted, server.credentials_dek_encrypted))

    # ------------------------------------------------------------------ endpoints

    async def add_manual_endpoint(
        self,
        namespace_id: uuid.UUID,
        name: str,
        operation_id: str,
        method: str,
        path: str,
        summary: str | None = None,
        param_schema: dict | None = None,
        request_body_schema: dict | None = None,
        response_schema: dict | None = None,
    ) -> ApiEndpoint:
        server = await self.get_by_name(namespace_id, name)
        method = method.upper()
        if method not in VALID_METHODS:
            raise ValidationError(f"invalid HTTP method '{method}'")
        if not _OPID_RE.match(operation_id):
            raise ValidationError(
                f"invalid operation_id '{operation_id}' (must be identifier-safe)"
            )
        existing = await self._endpoints(server.id)
        if any(ep.operation_id == operation_id for ep in existing):
            raise ConflictError(f"operation_id '{operation_id}' already exists on '{name}'")
        ep = ApiEndpoint(
            api_server_id=server.id,
            operation_id=operation_id,
            method=method,
            path=path,
            summary=summary,
            param_schema=param_schema or {},
            request_body_schema=request_body_schema,
            response_schema=response_schema,
            enabled=True,  # manual endpoints are deliberately defined → enabled
            source="manual",
        )
        self.db.add(ep)
        server.endpoint_count = len(existing) + 1
        await self.db.flush()
        await self.db.refresh(ep)
        return ep

    async def list_endpoints(
        self, namespace_id: uuid.UUID, name: str, filter_: str = "all"
    ) -> list[ApiEndpoint]:
        server = await self.get_by_name(namespace_id, name)
        endpoints = await self._endpoints(server.id)
        if filter_ == "enabled":
            return [e for e in endpoints if e.enabled]
        if filter_ == "published":
            return [e for e in endpoints if e.published]
        return endpoints

    async def set_enabled(
        self, namespace_id: uuid.UUID, name: str, operation_ids: list[str], enabled: bool
    ) -> list[str]:
        server = await self.get_by_name(namespace_id, name)
        endpoints = {ep.operation_id: ep for ep in await self._endpoints(server.id)}
        changed = []
        for oid in operation_ids:
            ep = endpoints.get(oid)
            if not ep:
                raise NotFoundError(f"endpoint '{oid}' not found on server '{name}'")
            ep.enabled = enabled
            changed.append(oid)
        await self.db.flush()
        return changed

    async def set_published(
        self, namespace_id: uuid.UUID, name: str, operation_id: str, published: bool
    ) -> ApiEndpoint:
        server = await self.get_by_name(namespace_id, name)
        endpoints = {ep.operation_id: ep for ep in await self._endpoints(server.id)}
        ep = endpoints.get(operation_id)
        if not ep:
            raise NotFoundError(f"endpoint '{operation_id}' not found on server '{name}'")
        ep.published = published
        await self.db.flush()
        await self.db.refresh(ep)
        return ep
