"""Centralized URL construction for configurable domain support.

All URL generation in the codebase should use these functions instead of
hardcoding mcpworks.io. Supports both path-based and subdomain-based routing
depending on ROUTING_MODE config.
"""

from __future__ import annotations

from functools import lru_cache


def _settings():
    from mcpworks_api.config import get_settings

    return get_settings()


def _is_path_mode() -> bool:
    return _settings().routing_mode in ("path", "both")


def _api_base() -> str:
    s = _settings()
    return f"{s.base_scheme}://api.{s.base_domain}"


def _subdomain_base(subdomain: str) -> str:
    s = _settings()
    return f"{s.base_scheme}://{subdomain}.{s.base_domain}"


def create_url(namespace: str) -> str:
    if _is_path_mode():
        return f"{_api_base()}/mcp/create/{namespace}"
    return _subdomain_base(f"{namespace}.create")


def run_url(namespace: str) -> str:
    if _is_path_mode():
        return f"{_api_base()}/mcp/run/{namespace}"
    return _subdomain_base(f"{namespace}.run")


def agent_url(agent_name: str) -> str:
    if _is_path_mode():
        return f"{_api_base()}/mcp/agent/{agent_name}"
    return _subdomain_base(f"{agent_name}.agent")


def mcp_url(namespace: str, endpoint: str = "run") -> str:
    if _is_path_mode():
        return f"{_api_base()}/mcp/{endpoint}/{namespace}"
    return f"{_subdomain_base(f'{namespace}.{endpoint}')}/mcp"


def api_url(path: str = "") -> str:
    base = _api_base()
    if path:
        return f"{base}{path}"
    return base


def view_url(agent_name: str, token: str) -> str:
    if _is_path_mode():
        return f"{_api_base()}/mcp/agent/{agent_name}/view/{token}/"
    return f"{_subdomain_base(f'{agent_name}.agent')}/view/{token}/"


def chat_url(agent_name: str, token: str) -> str:
    if _is_path_mode():
        return f"{_api_base()}/mcp/agent/{agent_name}/chat/{token}"
    return f"{_subdomain_base(f'{agent_name}.agent')}/chat/{token}"


def webhook_url(agent_name: str, path: str) -> str:
    if _is_path_mode():
        return f"{_api_base()}/mcp/agent/{agent_name}/webhook/{path}"
    return f"{_subdomain_base(f'{agent_name}.agent')}/webhook/{path}"


@lru_cache(maxsize=1)
def valid_suffixes() -> list[str]:
    s = _settings()
    if s.routing_mode in ("path", "both"):
        return ["/mcp/create/", "/mcp/run/", "/mcp/agent/"]
    return [
        f".create.{s.base_domain}",
        f".run.{s.base_domain}",
        f".agent.{s.base_domain}",
    ]
