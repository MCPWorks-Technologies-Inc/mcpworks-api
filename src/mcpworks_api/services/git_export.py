"""Namespace export serializer — converts DB entities to portable YAML + code files.

Produces the directory structure defined in spec REQ-EXP-001:
  {namespace}/
    namespace.yaml
    services/{service}/service.yaml
    services/{service}/functions/{function}/function.yaml
    services/{service}/functions/{function}/handler.py|ts
    agents/{agent}/agent.yaml
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from mcpworks_api.config import get_settings


def serialize_namespace(
    namespace_name: str,
    namespace_description: str | None,
    services: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    dest: str | Path,
) -> dict[str, int]:
    dest = Path(dest)
    ns_dir = dest / namespace_name

    if ns_dir.exists():
        for item in ns_dir.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    else:
        ns_dir.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    ns_manifest = {
        "apiVersion": "mcpworks/v1",
        "kind": "Namespace",
        "metadata": {
            "name": namespace_name,
            "description": namespace_description or "",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_from": getattr(settings, "base_domain", "localhost"),
            "mcpworks_version": "0.1.0",
        },
    }
    _write_yaml(ns_dir / "namespace.yaml", ns_manifest)

    func_count = 0
    for svc in services:
        svc_dir = ns_dir / "services" / svc["name"]
        svc_dir.mkdir(parents=True, exist_ok=True)
        svc_manifest = {
            "apiVersion": "mcpworks/v1",
            "kind": "Service",
            "metadata": {
                "name": svc["name"],
                "description": svc.get("description") or "",
            },
        }
        _write_yaml(svc_dir / "service.yaml", svc_manifest)

        for func in svc.get("functions", []):
            func_dir = svc_dir / "functions" / func["name"]
            func_dir.mkdir(parents=True, exist_ok=True)
            func_manifest = {
                "apiVersion": "mcpworks/v1",
                "kind": "Function",
                "metadata": {
                    "name": func["name"],
                    "description": func.get("description") or "",
                },
                "spec": {
                    "backend": func.get("backend", "code_sandbox"),
                    "language": func.get("language", "python"),
                    "requirements": func.get("requirements") or [],
                    "tags": func.get("tags") or [],
                    "public_safe": func.get("public_safe", False),
                    "locked": func.get("locked", False),
                    "input_schema": func.get("input_schema"),
                    "output_schema": func.get("output_schema"),
                    "env": {
                        "required": func.get("required_env") or [],
                        "optional": func.get("optional_env") or [],
                    },
                },
            }
            _write_yaml(func_dir / "function.yaml", func_manifest)

            code = func.get("code")
            if code:
                lang = func.get("language", "python")
                ext = "ts" if lang == "typescript" else "py"
                (func_dir / f"handler.{ext}").write_text(code, encoding="utf-8")

            func_count += 1

    agent_count = 0
    for agent in agents:
        agent_dir = ns_dir / "agents" / agent["name"]
        agent_dir.mkdir(parents=True, exist_ok=True)
        agent_manifest = {
            "apiVersion": "mcpworks/v1",
            "kind": "Agent",
            "metadata": {
                "name": agent["name"],
                "display_name": agent.get("display_name") or "",
            },
            "spec": {
                "ai_engine": agent.get("ai_engine"),
                "ai_model": agent.get("ai_model"),
                "system_prompt": agent.get("system_prompt"),
                "tool_tier": agent.get("tool_tier", "standard"),
                "scheduled_tool_tier": agent.get("scheduled_tool_tier", "execute_only"),
                "auto_channel": agent.get("auto_channel"),
                "memory_limit_mb": agent.get("memory_limit_mb", 256),
                "cpu_limit": agent.get("cpu_limit", 0.25),
                "heartbeat": {
                    "enabled": agent.get("heartbeat_enabled", False),
                    "interval": agent.get("heartbeat_interval"),
                },
                "orchestration_limits": agent.get("orchestration_limits"),
                "mcp_servers": agent.get("mcp_servers"),
                "schedules": [
                    {"name": s["name"], "cron": s["cron"], "enabled": s.get("enabled", True)}
                    for s in agent.get("schedules", [])
                ],
                "webhooks": [
                    {"name": w["name"], "enabled": w.get("enabled", True)}
                    for w in agent.get("webhooks", [])
                ],
                "channels": [
                    {"type": c["channel_type"]}
                    for c in agent.get("channels", [])
                ],
            },
        }
        _write_yaml(agent_dir / "agent.yaml", agent_manifest)
        agent_count += 1

    return {
        "services": len(services),
        "functions": func_count,
        "agents": agent_count,
    }


def serialize_service(
    service: dict[str, Any],
    dest: str | Path,
) -> int:
    dest = Path(dest)
    svc_dir = dest / "services" / service["name"]

    if svc_dir.exists():
        shutil.rmtree(svc_dir)

    svc_dir.mkdir(parents=True, exist_ok=True)
    svc_manifest = {
        "apiVersion": "mcpworks/v1",
        "kind": "Service",
        "metadata": {
            "name": service["name"],
            "description": service.get("description") or "",
        },
    }
    _write_yaml(svc_dir / "service.yaml", svc_manifest)

    func_count = 0
    for func in service.get("functions", []):
        func_dir = svc_dir / "functions" / func["name"]
        func_dir.mkdir(parents=True, exist_ok=True)
        func_manifest = {
            "apiVersion": "mcpworks/v1",
            "kind": "Function",
            "metadata": {
                "name": func["name"],
                "description": func.get("description") or "",
            },
            "spec": {
                "backend": func.get("backend", "code_sandbox"),
                "language": func.get("language", "python"),
                "requirements": func.get("requirements") or [],
                "tags": func.get("tags") or [],
                "public_safe": func.get("public_safe", False),
                "locked": func.get("locked", False),
                "input_schema": func.get("input_schema"),
                "output_schema": func.get("output_schema"),
                "env": {
                    "required": func.get("required_env") or [],
                    "optional": func.get("optional_env") or [],
                },
            },
        }
        _write_yaml(func_dir / "function.yaml", func_manifest)

        code = func.get("code")
        if code:
            lang = func.get("language", "python")
            ext = "ts" if lang == "typescript" else "py"
            (func_dir / f"handler.{ext}").write_text(code, encoding="utf-8")

        func_count += 1

    return func_count


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
