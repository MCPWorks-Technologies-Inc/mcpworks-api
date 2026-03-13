"""MCP client pool — connects agents to external MCP servers as clients."""

import asyncio
from contextlib import AsyncExitStack
from types import TracebackType

import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

logger = structlog.get_logger(__name__)

MCP_TOOL_PREFIX = "mcp__"


class McpServerPool:
    """Manages concurrent connections to multiple MCP servers.

    Usage::

        async with McpServerPool(agent.mcp_servers) as pool:
            tools = pool.get_tool_definitions()
            result = await pool.call_tool("mcp__weather__get_forecast", {"city": "Toronto"})
    """

    def __init__(self, servers: dict | None) -> None:
        self._server_configs = servers or {}
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, dict] = {}
        self._tool_to_server: dict[str, str] = {}
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "McpServerPool":
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        connect_tasks = []
        for name, config in self._server_configs.items():
            connect_tasks.append(self._connect_server(name, config))

        if connect_tasks:
            await asyncio.gather(*connect_tasks, return_exceptions=True)

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._stack:
            await self._stack.__aexit__(exc_type, exc_val, exc_tb)
        self._sessions.clear()
        self._tools.clear()
        self._tool_to_server.clear()

    async def _connect_server(self, name: str, config: dict) -> None:
        transport_type = config.get("type", "sse")
        try:
            if transport_type == "sse":
                read_stream, write_stream = await self._stack.enter_async_context(
                    sse_client(url=config["url"], headers=config.get("headers"))
                )
            elif transport_type == "streamable_http":
                read_stream, write_stream, _ = await self._stack.enter_async_context(
                    streamablehttp_client(url=config["url"], headers=config.get("headers"))
                )
            elif transport_type == "stdio":
                read_stream, write_stream = await self._stack.enter_async_context(
                    stdio_client(
                        command=config["command"],
                        args=config.get("args", []),
                        env=config.get("env"),
                    )
                )
            else:
                logger.warning("mcp_unknown_transport", server=name, transport=transport_type)
                return

            session = await self._stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            self._sessions[name] = session

            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                qualified_name = f"{MCP_TOOL_PREFIX}{name}__{tool.name}"
                self._tools[qualified_name] = {
                    "name": qualified_name,
                    "description": tool.description or f"MCP tool: {name}.{tool.name}",
                    "input_schema": tool.inputSchema
                    if tool.inputSchema
                    else {"type": "object", "properties": {}},
                }
                self._tool_to_server[qualified_name] = name

            logger.info(
                "mcp_server_connected",
                server=name,
                transport=transport_type,
                tools_count=len(tools_result.tools),
            )
        except Exception:
            logger.exception("mcp_server_connect_failed", server=name)

    def get_tool_definitions(self) -> list[dict]:
        return list(self._tools.values())

    async def call_tool(self, qualified_name: str, arguments: dict) -> str:
        server_name = self._tool_to_server.get(qualified_name)
        if not server_name:
            return f'{{"error": "Unknown MCP tool: {qualified_name}"}}'

        session = self._sessions.get(server_name)
        if not session:
            return f'{{"error": "MCP server not connected: {server_name}"}}'

        parts = qualified_name.split("__", 2)
        if len(parts) < 3:
            return f'{{"error": "Invalid MCP tool name format: {qualified_name}"}}'
        tool_name = parts[2]

        try:
            result = await session.call_tool(tool_name, arguments)
            text_parts = []
            for content in result.content:
                if hasattr(content, "text"):
                    text_parts.append(content.text)
                elif hasattr(content, "data"):
                    text_parts.append(f"[binary data: {content.mimeType}]")
            output = "\n".join(text_parts) if text_parts else ""
            return output[:4000]
        except Exception as e:
            logger.exception("mcp_tool_call_failed", tool=qualified_name)
            return f'{{"error": "MCP tool call failed: {str(e)[:300]}"}}'


def is_mcp_tool(name: str) -> bool:
    return name.startswith(MCP_TOOL_PREFIX)
