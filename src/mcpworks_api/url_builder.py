"""Centralized URL construction for configurable domain support.

All URL generation in the codebase should use these functions instead of
hardcoding mcpworks.io. Reads BASE_DOMAIN and BASE_SCHEME from settings.
"""

from __future__ import annotations

from functools import lru_cache


def _settings():
    from mcpworks_api.config import get_settings

    return get_settings()


def _base(subdomain: str) -> str:
    s = _settings()
    return f"{s.base_scheme}://{subdomain}.{s.base_domain}"


def create_url(namespace: str) -> str:
    return _base(f"{namespace}.create")


def run_url(namespace: str) -> str:
    return _base(f"{namespace}.run")


def agent_url(agent_name: str) -> str:
    return _base(f"{agent_name}.agent")


def mcp_url(namespace: str, endpoint: str = "run") -> str:
    return f"{_base(f'{namespace}.{endpoint}')}/mcp"


def api_url(path: str = "") -> str:
    s = _settings()
    base = f"{s.base_scheme}://api.{s.base_domain}"
    if path:
        return f"{base}{path}"
    return base


def view_url(agent_name: str, token: str) -> str:
    return f"{agent_url(agent_name)}/view/{token}/"


def chat_url(agent_name: str, token: str) -> str:
    return f"{agent_url(agent_name)}/chat/{token}"


@lru_cache(maxsize=1)
def valid_suffixes() -> list[str]:
    s = _settings()
    return [
        f".create.{s.base_domain}",
        f".run.{s.base_domain}",
        f".agent.{s.base_domain}",
    ]
