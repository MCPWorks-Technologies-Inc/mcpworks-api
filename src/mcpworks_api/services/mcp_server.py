"""MCP server registry service — CRUD, discovery, settings, env vars."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.encryption import decrypt_value, encrypt_value
from mcpworks_api.core.exceptions import ConflictError, NotFoundError
from mcpworks_api.models.namespace_mcp_server import NamespaceMcpServer

logger = structlog.get_logger(__name__)

VALID_SETTINGS_KEYS = {
    "response_limit_bytes": int,
    "timeout_seconds": int,
    "max_calls_per_execution": int,
    "retry_on_failure": bool,
    "retry_count": int,
}


class McpServerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add_server(
        self,
        namespace_id: uuid.UUID,
        name: str,
        url: str | None = None,
        transport: str = "streamable_http",
        auth_token: str | None = None,
        headers: dict[str, str] | None = None,
        command: str | None = None,
        args: list[str] | None = None,
    ) -> NamespaceMcpServer:
        existing = await self._get_by_name_optional(namespace_id, name)
        if existing:
            raise ConflictError(f"MCP server '{name}' already exists in this namespace")

        all_headers = dict(headers or {})
        if auth_token:
            all_headers["Authorization"] = f"Bearer {auth_token}"

        headers_enc = None
        headers_dek = None
        if all_headers:
            headers_enc, headers_dek = encrypt_value(all_headers)

        tool_schemas, tool_count = await self._discover_tools(
            url=url,
            transport=transport,
            headers=all_headers if all_headers else None,
            command=command,
            args=args,
        )

        default_rules = {
            "request": [],
            "response": [
                {"id": "default-trust", "type": "wrap_trust_boundary", "tools": "*"},
                {
                    "id": "default-scan",
                    "type": "scan_injection",
                    "tools": "*",
                    "strictness": "warn",
                },
            ],
        }

        server = NamespaceMcpServer(
            namespace_id=namespace_id,
            name=name,
            transport=transport,
            url=url,
            command=command,
            command_args=args,
            headers_encrypted=headers_enc,
            headers_dek_encrypted=headers_dek,
            settings={},
            env_vars={},
            rules=default_rules,
            tool_schemas=tool_schemas,
            tool_count=tool_count,
            last_connected_at=datetime.now(UTC),
        )
        self.db.add(server)
        await self.db.flush()
        await self.db.refresh(server)

        logger.info(
            "mcp_server_added",
            namespace_id=str(namespace_id),
            name=name,
            transport=transport,
            tool_count=tool_count,
        )
        return server

    async def remove_server(self, namespace_id: uuid.UUID, name: str) -> None:
        server = await self.get_by_name(namespace_id, name)
        await self.db.delete(server)
        await self.db.flush()
        logger.info("mcp_server_removed", namespace_id=str(namespace_id), name=name)

    async def list_servers(self, namespace_id: uuid.UUID) -> list[NamespaceMcpServer]:
        stmt = (
            select(NamespaceMcpServer)
            .where(NamespaceMcpServer.namespace_id == namespace_id)
            .order_by(NamespaceMcpServer.name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, namespace_id: uuid.UUID, name: str) -> NamespaceMcpServer:
        server = await self._get_by_name_optional(namespace_id, name)
        if not server:
            raise NotFoundError(f"MCP server '{name}' not found")
        return server

    async def refresh_server(
        self, namespace_id: uuid.UUID, name: str
    ) -> tuple[NamespaceMcpServer, list[str], list[str]]:
        server = await self.get_by_name(namespace_id, name)
        headers = self._decrypt_headers(server)

        new_schemas, new_count = await self._discover_tools(
            url=server.url,
            transport=server.transport,
            headers=headers,
            command=server.command,
            args=server.command_args,
        )

        old_names = {t["name"] for t in (server.tool_schemas or [])}
        new_names = {t["name"] for t in new_schemas}
        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)

        server.tool_schemas = new_schemas
        server.tool_count = new_count
        server.last_connected_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.refresh(server)

        logger.info(
            "mcp_server_refreshed",
            name=name,
            tool_count=new_count,
            added=len(added),
            removed=len(removed),
        )
        return server, added, removed

    async def update_server(
        self,
        namespace_id: uuid.UUID,
        name: str,
        auth_token: str | None = None,
        headers: dict[str, str] | None = None,
        url: str | None = None,
    ) -> NamespaceMcpServer:
        server = await self.get_by_name(namespace_id, name)
        if url:
            server.url = url
        if auth_token or headers:
            all_headers = dict(headers or {})
            if auth_token:
                all_headers["Authorization"] = f"Bearer {auth_token}"
            if all_headers:
                enc, dek = encrypt_value(all_headers)
                server.headers_encrypted = enc
                server.headers_dek_encrypted = dek
        await self.db.flush()
        await self.db.refresh(server)
        logger.info("mcp_server_updated", name=name)
        return server

    async def set_setting(self, namespace_id: uuid.UUID, name: str, key: str, value: Any) -> dict:
        if key == "enabled":
            server = await self.get_by_name(namespace_id, name)
            server.enabled = bool(value)
            await self.db.flush()
            await self.db.refresh(server)
            return server.get_settings()

        if key not in VALID_SETTINGS_KEYS:
            raise ValueError(
                f"Unknown setting '{key}'. Valid: {', '.join(sorted(VALID_SETTINGS_KEYS))}"
            )
        expected_type = VALID_SETTINGS_KEYS[key]
        if not isinstance(value, expected_type):
            raise ValueError(f"Setting '{key}' must be {expected_type.__name__}")

        server = await self.get_by_name(namespace_id, name)
        settings = dict(server.settings or {})
        settings[key] = value
        server.settings = settings
        await self.db.flush()
        await self.db.refresh(server)
        return server.get_settings()

    async def set_env(self, namespace_id: uuid.UUID, name: str, key: str, value: str) -> dict:
        server = await self.get_by_name(namespace_id, name)
        env = dict(server.env_vars or {})
        env[key] = value
        server.env_vars = env
        await self.db.flush()
        await self.db.refresh(server)
        return dict(server.env_vars)

    async def remove_env(self, namespace_id: uuid.UUID, name: str, key: str) -> dict:
        server = await self.get_by_name(namespace_id, name)
        env = dict(server.env_vars or {})
        env.pop(key, None)
        server.env_vars = env
        await self.db.flush()
        await self.db.refresh(server)
        return dict(server.env_vars)

    async def add_rule(
        self, namespace_id: uuid.UUID, name: str, direction: str, rule: dict
    ) -> dict:
        if direction not in ("request", "response"):
            raise ValueError("direction must be 'request' or 'response'")
        server = await self.get_by_name(namespace_id, name)
        rules = dict(server.rules or {"request": [], "response": []})
        rule_id = rule.get("id") or f"r-{uuid.uuid4().hex[:8]}"
        rule["id"] = rule_id
        rules.setdefault(direction, []).append(rule)
        server.rules = rules
        await self.db.flush()
        await self.db.refresh(server)
        return {"rule_id": rule_id, "rule": rule}

    async def remove_rule(self, namespace_id: uuid.UUID, name: str, rule_id: str) -> None:
        server = await self.get_by_name(namespace_id, name)
        rules = dict(server.rules or {"request": [], "response": []})
        for direction in ("request", "response"):
            rules[direction] = [r for r in rules.get(direction, []) if r.get("id") != rule_id]
        server.rules = rules
        await self.db.flush()
        await self.db.refresh(server)

    async def list_rules(self, namespace_id: uuid.UUID, name: str) -> dict:
        server = await self.get_by_name(namespace_id, name)
        rules = server.rules or {"request": [], "response": []}
        return {
            "request_rules": rules.get("request", []),
            "response_rules": rules.get("response", []),
        }

    def _decrypt_headers(self, server: NamespaceMcpServer) -> dict[str, str] | None:
        if not server.headers_encrypted:
            return None
        return decrypt_value(server.headers_encrypted, server.headers_dek_encrypted)

    async def _get_by_name_optional(
        self, namespace_id: uuid.UUID, name: str
    ) -> NamespaceMcpServer | None:
        stmt = select(NamespaceMcpServer).where(
            NamespaceMcpServer.namespace_id == namespace_id,
            NamespaceMcpServer.name == name,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _discover_tools(
        self,
        url: str | None,
        transport: str,
        headers: dict[str, str] | None = None,
        command: str | None = None,
        args: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        from contextlib import AsyncExitStack

        from mcp import ClientSession
        from mcp.client.sse import sse_client
        from mcp.client.streamable_http import streamablehttp_client

        stack = AsyncExitStack()
        try:
            async with stack:
                if transport == "sse":
                    read_stream, write_stream = await stack.enter_async_context(
                        sse_client(url=url, headers=headers)
                    )
                elif transport == "streamable_http":
                    read_stream, write_stream, _ = await stack.enter_async_context(
                        streamablehttp_client(url=url, headers=headers)
                    )
                elif transport == "stdio":
                    from mcp.client.stdio import stdio_client

                    read_stream, write_stream = await stack.enter_async_context(
                        stdio_client(command=command, args=args or [])
                    )
                else:
                    raise ValueError(f"Unsupported transport: {transport}")

                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await session.initialize()
                tools_result = await session.list_tools()

                schemas = []
                for tool in tools_result.tools:
                    schemas.append(
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "input_schema": tool.inputSchema
                            if tool.inputSchema
                            else {"type": "object", "properties": {}},
                        }
                    )

                logger.info(
                    "mcp_tools_discovered",
                    transport=transport,
                    tool_count=len(schemas),
                )
                return schemas, len(schemas)
        except Exception as e:
            logger.error("mcp_discovery_failed", transport=transport, error=str(e)[:300])
            raise
