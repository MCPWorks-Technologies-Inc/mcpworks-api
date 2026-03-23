"""Agent orchestration loop — trigger -> AI -> tools -> channel output.

Runs server-side in the API process. When a trigger fires with
orchestration_mode != "direct", this module invokes the agent's AI model,
presents namespace functions as callable tools, and dispatches tool calls
back through the sandbox backend.
"""

import json
import time
import uuid as uuid_mod
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.backends import get_backend
from mcpworks_api.core.ai_client import AIClientError, chat_with_tools
from mcpworks_api.core.ai_tools import (
    PLATFORM_TOOL_NAMES,
    augment_system_prompt,
    build_tool_definitions,
    format_available_tools,
    parse_tool_name,
)
from mcpworks_api.core.context_budget import estimate_context_budget
from mcpworks_api.core.database import get_db_context
from mcpworks_api.core.encryption import decrypt_value
from mcpworks_api.core.mcp_client import McpServerPool, is_mcp_tool
from mcpworks_api.core.telemetry import make_event, telemetry_bus
from mcpworks_api.models.account import Account
from mcpworks_api.models.agent import Agent, AgentChannel, AgentRun
from mcpworks_api.services.agent_service import AgentService
from mcpworks_api.services.function import FunctionService

logger = structlog.get_logger(__name__)

ORCHESTRATION_TIER_LIMITS: dict[str, dict] = {
    "trial-agent": {
        "max_iterations": 10,
        "max_ai_tokens": 200_000,
        "max_execution_seconds": 120,
        "max_functions_called": 10,
    },
    "pro-agent": {
        "max_iterations": 10,
        "max_ai_tokens": 200_000,
        "max_execution_seconds": 120,
        "max_functions_called": 10,
    },
    "enterprise-agent": {
        "max_iterations": 25,
        "max_ai_tokens": 1_000_000,
        "max_execution_seconds": 300,
        "max_functions_called": 25,
    },
    "dedicated-agent": {
        "max_iterations": 50,
        "max_ai_tokens": 2_000_000,
        "max_execution_seconds": 300,
        "max_functions_called": -1,
    },
}

DEFAULT_LIMITS = {
    "max_iterations": 10,
    "max_ai_tokens": 200_000,
    "max_execution_seconds": 120,
    "max_functions_called": 10,
}

VALID_LIMIT_KEYS = frozenset(DEFAULT_LIMITS.keys())


def resolve_orchestration_limits(tier: str, agent: Agent) -> dict:
    """Merge tier defaults with per-agent overrides."""
    limits = dict(ORCHESTRATION_TIER_LIMITS.get(tier, DEFAULT_LIMITS))
    overrides = agent.orchestration_limits
    if overrides:
        for key, value in overrides.items():
            if key in VALID_LIMIT_KEYS and isinstance(value, int):
                limits[key] = value
    return limits


@dataclass
class OrchestrationResult:
    success: bool
    final_text: str | None
    functions_called: list[str] = field(default_factory=list)
    iterations: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    error: str | None = None
    context_tokens: int = 0


async def run_orchestration(
    agent: Agent,
    trigger_type: str,
    trigger_context: str,
    trigger_data: dict,  # noqa: ARG001  — reserved for future use (logging, state)
    tier: str,
    account: Account,
) -> OrchestrationResult:
    """Execute the AI orchestration loop for an agent."""
    start_time = time.monotonic()
    limits = resolve_orchestration_limits(tier, agent)

    if not agent.ai_engine or not agent.ai_api_key_encrypted:
        return OrchestrationResult(
            success=False,
            final_text=None,
            error="Agent has no AI engine configured",
            duration_ms=_elapsed_ms(start_time),
        )

    api_key = decrypt_value(agent.ai_api_key_encrypted, agent.ai_api_key_dek_encrypted)

    async with get_db_context() as db:
        tools = await build_tool_definitions(agent.namespace_id, db)
        agent_state = await AgentService(db).get_all_state(agent.id)

    mcp_pool: McpServerPool | None = None
    if agent.mcp_servers:
        try:
            mcp_pool = McpServerPool(agent.mcp_servers)
            await mcp_pool.__aenter__()
            tools.extend(mcp_pool.get_tool_definitions())
            logger.info(
                "orchestration_mcp_tools_loaded",
                agent_name=agent.name,
                mcp_tools_count=len(mcp_pool.get_tool_definitions()),
            )
        except Exception:
            logger.exception("orchestration_mcp_pool_failed", agent_name=agent.name)
            mcp_pool = None

    from mcpworks_api.core.conversation_memory import load_history

    effective_system_prompt = augment_system_prompt(agent.system_prompt, tools)

    # Inject conversation summary into orchestration context (lightweight)
    summary, _ = load_history(agent_state)
    if summary:
        effective_system_prompt += f"\n\n## Recent conversation context\n{summary}"

    messages: list[dict] = [{"role": "user", "content": trigger_context}]
    functions_called: list[str] = []
    total_tokens = 0
    iterations = 0
    consecutive_failures = 0
    max_consecutive_failures = 3
    agent_id_str = str(agent.id)
    run_id = str(uuid_mod.uuid4())

    def _emit(etype: str, **kw: object) -> None:
        telemetry_bus.emit(agent_id_str, make_event(etype, agent_id_str, run_id, **kw))

    _emit(
        "orchestration_start",
        trigger_type=trigger_type,
        tools_count=len(tools),
        mcp_servers_count=len(agent.mcp_servers or {}),
    )

    budget = estimate_context_budget(effective_system_prompt, messages, tools)
    context_tokens = budget["total_estimated_tokens"]
    _emit("context_budget", **budget)
    if budget["level"] in ("orange", "red"):
        logger.warning(
            "orchestration_context_budget_high",
            agent_name=agent.name,
            level=budget["level"],
            total_tokens=context_tokens,
        )

    try:
        while iterations < limits["max_iterations"]:
            if total_tokens >= limits["max_ai_tokens"]:
                return _limit_result(
                    "Token limit exceeded",
                    functions_called,
                    iterations,
                    total_tokens,
                    start_time,
                    context_tokens,
                )
            if _elapsed_seconds(start_time) >= limits["max_execution_seconds"]:
                return _limit_result(
                    "Execution time limit exceeded",
                    functions_called,
                    iterations,
                    total_tokens,
                    start_time,
                    context_tokens,
                )

            response = await chat_with_tools(
                engine=agent.ai_engine,
                model=agent.ai_model or "",
                api_key=api_key,
                messages=messages,
                tools=tools,
                system_prompt=effective_system_prompt,
            )
            iterations += 1
            usage = response.get("usage", {})
            total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            _emit("ai_thinking", iteration=iterations, usage=usage)

            content_blocks = response.get("content", [])
            stop_reason = response.get("stop_reason", "end_turn")

            for block in content_blocks:
                if block.get("type") == "text" and block.get("text"):
                    _emit("ai_text", text=block["text"][:500])

            if stop_reason != "tool_use":
                final_text = _extract_text(content_blocks)
                result = OrchestrationResult(
                    success=True,
                    final_text=final_text,
                    functions_called=functions_called,
                    iterations=iterations,
                    total_tokens=total_tokens,
                    duration_ms=_elapsed_ms(start_time),
                    context_tokens=context_tokens,
                )
                _emit(
                    "completion",
                    success=True,
                    iterations=iterations,
                    functions_called=functions_called,
                    total_tokens=total_tokens,
                )
                await _post_orchestration(agent, trigger_type, result)
                return result

            messages.append({"role": "assistant", "content": content_blocks})

            tool_results = []
            iteration_had_success = False
            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue

                tool_name = block["name"]
                tool_input = block.get("input", {})
                tool_id = block["id"]

                if (
                    limits["max_functions_called"] >= 0
                    and len(functions_called) >= limits["max_functions_called"]
                ):
                    tool_results.append(
                        _tool_result(
                            tool_id,
                            tool_name,
                            json.dumps(
                                {
                                    "error": f"Function call limit reached ({limits['max_functions_called']}). "
                                    "You have already called enough functions. Summarize your results and finish.",
                                }
                            ),
                        )
                    )
                    continue

                source = (
                    "mcp"
                    if is_mcp_tool(tool_name)
                    else ("platform" if tool_name in PLATFORM_TOOL_NAMES else "namespace")
                )
                _emit("tool_call", name=tool_name, args=tool_input, source=source)
                tc_start = time.monotonic()
                result_str = await _dispatch_tool(
                    tool_name,
                    tool_input,
                    agent,
                    account,
                    tier,
                    mcp_pool=mcp_pool,
                    agent_state=agent_state,
                    trigger_type=trigger_type,
                    available_tools=tools,
                )
                _emit(
                    "tool_result",
                    name=tool_name,
                    result_preview=result_str[:200],
                    duration_ms=_elapsed_ms(tc_start),
                )

                is_error = '"error"' in result_str[:50]
                if not is_error:
                    functions_called.append(tool_name)
                    iteration_had_success = True

                tool_results.append(_tool_result(tool_id, tool_name, result_str))

            messages.extend(tool_results)

            if iteration_had_success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    return _limit_result(
                        f"Stopped after {consecutive_failures} consecutive iterations "
                        "where all tool calls failed. The AI model may not be "
                        "using the correct tool name format.",
                        functions_called,
                        iterations,
                        total_tokens,
                        start_time,
                        context_tokens,
                    )

        return _limit_result(
            "Max iterations exceeded",
            functions_called,
            iterations,
            total_tokens,
            start_time,
            context_tokens,
        )

    except AIClientError as e:
        _emit("error", message=str(e)[:300], phase="ai_call")
        logger.error(
            "orchestration_ai_error",
            agent_name=agent.name,
            engine=agent.ai_engine,
            iterations=iterations,
        )
        result = OrchestrationResult(
            success=False,
            final_text=None,
            functions_called=functions_called,
            iterations=iterations,
            total_tokens=total_tokens,
            duration_ms=_elapsed_ms(start_time),
            error=str(e)[:500],
        )
        await _record_run(agent, trigger_type, result)
        return result
    except Exception as e:
        _emit("error", message=str(e)[:300], phase="orchestration")
        logger.exception("orchestration_unexpected_error", agent_name=agent.name)
        result = OrchestrationResult(
            success=False,
            final_text=None,
            functions_called=functions_called,
            iterations=iterations,
            total_tokens=total_tokens,
            duration_ms=_elapsed_ms(start_time),
            error=str(e)[:500],
        )
        await _record_run(agent, trigger_type, result)
        return result
    finally:
        if mcp_pool is not None:
            try:
                await mcp_pool.__aexit__(None, None, None)
            except Exception:
                logger.exception("orchestration_mcp_pool_cleanup_failed")


async def _dispatch_tool(
    tool_name: str,
    tool_input: dict,
    agent: Agent,
    account: Account,
    tier: str,
    mcp_pool: McpServerPool | None = None,
    agent_state: dict | None = None,
    trigger_type: str = "manual",
    available_tools: list[dict] | None = None,
) -> str:
    """Dispatch a tool call to a platform tool, MCP tool, or namespace function."""
    from mcpworks_api.core.tool_permissions import ToolTier, is_tool_allowed

    if trigger_type in ("cron", "webhook"):
        effective_tier = ToolTier(getattr(agent, "scheduled_tool_tier", "execute_only"))
    else:
        effective_tier = ToolTier(getattr(agent, "tool_tier", "standard"))

    if not is_tool_allowed(effective_tier, tool_name):
        return json.dumps(
            {
                "error": f"Agent '{agent.name}' (tier: {effective_tier.value}) "
                f"is not authorized to call '{tool_name}' in {trigger_type} context"
            }
        )

    if tool_name in PLATFORM_TOOL_NAMES:
        return await _execute_platform_tool(
            tool_name, tool_input, agent, account, tier, agent_state=agent_state
        )

    if is_mcp_tool(tool_name):
        if mcp_pool is None:
            return json.dumps({"error": "MCP server pool not available"})
        return await mcp_pool.call_tool(tool_name, tool_input)

    parsed = parse_tool_name(tool_name)
    if not parsed:
        available = format_available_tools(available_tools) if available_tools else "none"
        return json.dumps(
            {
                "error": f"Unknown tool: '{tool_name}'. Tool names use the format "
                "'service_name__function_name' (double underscore). "
                f"Available tools: {available}",
            }
        )

    service_name, function_name = parsed
    return await _execute_namespace_function(
        service_name,
        function_name,
        tool_input,
        agent,
        account,
        agent_state=agent_state,
    )


async def _execute_platform_tool(
    tool_name: str,
    tool_input: dict,
    agent: Agent,
    account: Account,
    tier: str,
    agent_state: dict | None = None,
) -> str:
    """Execute a built-in platform tool."""
    try:
        if tool_name == "send_to_channel":
            return await _send_to_channel(
                agent,
                tool_input.get("channel_type", ""),
                tool_input.get("message", ""),
            )
        elif tool_name == "get_state":
            async with get_db_context() as db:
                service = AgentService(db)
                value, _ = await service.get_state(
                    account.id,
                    agent.name,
                    tool_input.get("key", ""),
                )
                return json.dumps({"key": tool_input.get("key"), "value": value})
        elif tool_name == "set_state":
            async with get_db_context() as db:
                service = AgentService(db)
                await service.set_state(
                    account.id,
                    agent.name,
                    tool_input.get("key", ""),
                    tool_input.get("value"),
                    tier,
                )
                return json.dumps({"key": tool_input.get("key"), "stored": True})
        elif tool_name == "list_state_keys":
            async with get_db_context() as db:
                service = AgentService(db)
                keys_info = await service.list_state_keys(account.id, agent.name, tier)
                return json.dumps(
                    {
                        "keys": keys_info["keys"],
                        "count": len(keys_info["keys"]),
                        "total_size_bytes": keys_info["total_size_bytes"],
                    }
                )
        elif tool_name == "search_state":
            query = tool_input.get("query", "").lower()
            if not query:
                return json.dumps({"error": "query is required"})
            matches = []
            for key, value in (agent_state or {}).items():
                value_str = json.dumps(value, default=str) if not isinstance(value, str) else value
                if query in key.lower() or query in value_str.lower():
                    preview = value_str[:100] + ("..." if len(value_str) > 100 else "")
                    matches.append({"key": key, "preview": preview})
            return json.dumps(
                {
                    "matches": matches[:20],
                    "query": query,
                    "total_searched": len(agent_state or {}),
                }
            )
        else:
            return json.dumps({"error": f"Unknown platform tool: {tool_name}"})
    except Exception as e:
        return json.dumps({"error": str(e)[:500]})


async def _execute_namespace_function(
    service_name: str,
    function_name: str,
    input_data: dict,
    agent: Agent,
    account: Account,
    agent_state: dict | None = None,
    db: AsyncSession | None = None,
) -> str:
    """Execute a namespace function via the sandbox backend."""
    try:
        if db is not None:
            function_service = FunctionService(db)
            _, version = await function_service.get_for_execution(
                namespace_id=agent.namespace_id,
                service_name=service_name,
                function_name=function_name,
            )
        else:
            async with get_db_context() as new_db:
                function_service = FunctionService(new_db)
                _, version = await function_service.get_for_execution(
                    namespace_id=agent.namespace_id,
                    service_name=service_name,
                    function_name=function_name,
                )

        backend = get_backend(version.backend)
        if not backend:
            return json.dumps({"error": f"Backend not available: {version.backend}"})

        context = {"state": agent_state or {}}

        execution_id = str(uuid_mod.uuid4())
        result = await backend.execute(
            code=version.code,
            config=version.config,
            input_data=input_data,
            account=account,
            execution_id=execution_id,
            context=context,
            namespace=agent.name,
        )

        if result.success:
            try:
                await _increment_orchestration_call_count(
                    agent.namespace_id, service_name, function_name
                )
            except Exception:
                logger.warning(
                    "orchestration_call_count_failed", service=service_name, function=function_name
                )
            output = result.output
            if isinstance(output, str):
                return output[:4000]
            return json.dumps(output, default=str)[:4000]
        else:
            return json.dumps({"error": result.error or "Function execution failed"})
    except Exception as e:
        return json.dumps({"error": str(e)[:500]})


async def _increment_orchestration_call_count(
    namespace_id: uuid_mod.UUID,
    service_name: str,
    function_name: str,
) -> None:
    """Increment call_count on namespace, service, and function after orchestration execution."""
    from mcpworks_api.models.function import Function
    from mcpworks_api.models.namespace import Namespace
    from mcpworks_api.models.namespace_service import NamespaceService

    async with get_db_context() as db:
        await db.execute(select(Namespace).where(Namespace.id == namespace_id))
        from sqlalchemy import update as sa_update

        await db.execute(
            sa_update(Namespace)
            .where(Namespace.id == namespace_id)
            .values(call_count=Namespace.call_count + 1)
        )
        await db.execute(
            sa_update(NamespaceService)
            .where(
                NamespaceService.namespace_id == namespace_id,
                NamespaceService.name == service_name,
            )
            .values(call_count=NamespaceService.call_count + 1)
        )
        await db.execute(
            sa_update(Function)
            .where(
                Function.service_id == NamespaceService.id,
                NamespaceService.namespace_id == namespace_id,
                NamespaceService.name == service_name,
                Function.name == function_name,
            )
            .values(call_count=Function.call_count + 1)
        )


async def _send_to_channel(
    agent: Agent,
    channel_type: str,
    message: str,
) -> str:
    """Send a message to a configured channel."""
    import httpx

    async with get_db_context() as db:
        result = await db.execute(
            select(AgentChannel).where(
                AgentChannel.agent_id == agent.id,
                AgentChannel.channel_type == channel_type,
                AgentChannel.enabled.is_(True),
            )
        )
        channel = result.scalar_one_or_none()

    if not channel:
        return json.dumps({"error": f"Channel not configured: {channel_type}"})

    config = decrypt_value(channel.config_encrypted, channel.config_dek_encrypted)

    if channel_type == "discord":
        webhook_url = config.get("webhook_url") if isinstance(config, dict) else None
        if not webhook_url:
            return json.dumps({"error": "Discord channel missing webhook_url in config"})
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json={"content": message[:2000]})
            if resp.status_code < 300:
                return json.dumps({"sent": True, "channel": channel_type})
            return json.dumps({"error": f"Discord webhook returned {resp.status_code}"})
        except Exception as e:
            return json.dumps({"error": f"Discord send failed: {str(e)[:200]}"})
    else:
        return json.dumps({"error": f"Channel type '{channel_type}' not yet supported"})


async def _post_orchestration(
    agent: Agent,
    trigger_type: str,
    result: OrchestrationResult,
) -> None:
    """Handle post-orchestration tasks: auto_channel, run recording."""
    if result.success and agent.auto_channel and result.final_text:
        try:
            await _send_to_channel(agent, agent.auto_channel, result.final_text)
        except Exception:
            logger.exception("auto_channel_send_failed", agent_name=agent.name)

    await _record_run(agent, trigger_type, result)


async def _record_run(
    agent: Agent,
    trigger_type: str,
    result: OrchestrationResult,
) -> None:
    """Record an orchestration run as an AgentRun."""
    try:
        async with get_db_context() as db:
            run = AgentRun(
                agent_id=agent.id,
                trigger_type="ai",
                trigger_detail=f"orchestration:{trigger_type}",
                function_name=", ".join(result.functions_called[:10]) or None,
                status="completed" if result.success else "failed",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                duration_ms=result.duration_ms,
                result_summary=result.final_text[:1000] if result.final_text else None,
                error=result.error[:1000] if result.error else None,
            )
            db.add(run)
    except Exception:
        logger.exception("orchestration_run_record_failed", agent_name=agent.name)


def _tool_result(tool_id: str, tool_name: str, content: str) -> dict:
    return {
        "role": "tool_result",
        "tool_use_id": tool_id,
        "tool_name": tool_name,
        "content": content,
    }


def _extract_text(content_blocks: list[dict]) -> str | None:
    texts = [b["text"] for b in content_blocks if b.get("type") == "text" and b.get("text")]
    return "\n".join(texts) if texts else None


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _elapsed_seconds(start: float) -> float:
    return time.monotonic() - start


def _limit_result(
    error: str,
    functions_called: list[str],
    iterations: int,
    total_tokens: int,
    start_time: float,
    context_tokens: int = 0,
) -> OrchestrationResult:
    return OrchestrationResult(
        success=False,
        final_text=None,
        functions_called=functions_called,
        iterations=iterations,
        total_tokens=total_tokens,
        duration_ms=_elapsed_ms(start_time),
        error=error,
        context_tokens=context_tokens,
    )
