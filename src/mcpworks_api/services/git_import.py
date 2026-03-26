"""Namespace import deserializer — reads portable YAML + code files into data structures.

Validates all manifests before returning, per REQ-SEC-003.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ImportValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Import validation failed: {'; '.join(errors)}")


def validate_and_parse(directory: str | Path) -> dict[str, Any]:
    directory = Path(directory)
    errors: list[str] = []

    ns_dirs = [d for d in directory.iterdir() if d.is_dir() and d.name != ".git"]
    if len(ns_dirs) == 0:
        ns_yaml = directory / "namespace.yaml"
        if ns_yaml.exists():
            ns_dir = directory
        else:
            raise ImportValidationError(["No namespace directory or namespace.yaml found"])
    elif len(ns_dirs) == 1:
        ns_dir = ns_dirs[0]
        if not (ns_dir / "namespace.yaml").exists():
            ns_dir = directory
            if not (ns_dir / "namespace.yaml").exists():
                raise ImportValidationError([f"No namespace.yaml in {ns_dir}"])
    else:
        for d in ns_dirs:
            if (d / "namespace.yaml").exists():
                ns_dir = d
                break
        else:
            raise ImportValidationError(["Multiple directories found, none with namespace.yaml"])

    ns_yaml = _load_yaml(ns_dir / "namespace.yaml", errors)
    if ns_yaml is None:
        raise ImportValidationError(errors)

    if ns_yaml.get("apiVersion") != "mcpworks/v1":
        errors.append(f"Unsupported apiVersion: {ns_yaml.get('apiVersion')}")
    if ns_yaml.get("kind") != "Namespace":
        errors.append(f"Expected kind: Namespace, got: {ns_yaml.get('kind')}")

    metadata = ns_yaml.get("metadata", {})
    ns_name = metadata.get("name")
    if not ns_name:
        errors.append("namespace.yaml missing metadata.name")

    services = _parse_services(ns_dir / "services", errors)
    agents = _parse_agents(ns_dir / "agents", errors)

    if errors:
        raise ImportValidationError(errors)

    return {
        "name": ns_name,
        "description": metadata.get("description"),
        "services": services,
        "agents": agents,
    }


def parse_service(directory: str | Path, service_name: str) -> dict[str, Any]:
    directory = Path(directory)
    errors: list[str] = []

    ns_dirs = [d for d in directory.iterdir() if d.is_dir() and d.name != ".git"]
    svc_dir = None

    for ns_dir in [directory, *ns_dirs]:
        candidate = ns_dir / "services" / service_name
        if candidate.is_dir():
            svc_dir = candidate
            break

    if svc_dir is None:
        raise ImportValidationError([f"Service '{service_name}' not found in export"])

    svc = _parse_single_service(svc_dir, errors)
    if errors:
        raise ImportValidationError(errors)
    return svc


def _parse_services(services_dir: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not services_dir.is_dir():
        return []

    services = []
    for svc_dir in sorted(services_dir.iterdir()):
        if not svc_dir.is_dir():
            continue
        svc = _parse_single_service(svc_dir, errors)
        if svc:
            services.append(svc)
    return services


def _parse_single_service(svc_dir: Path, errors: list[str]) -> dict[str, Any] | None:
    svc_yaml_path = svc_dir / "service.yaml"
    if not svc_yaml_path.exists():
        errors.append(f"Missing service.yaml in {svc_dir.name}")
        return None

    svc_yaml = _load_yaml(svc_yaml_path, errors)
    if svc_yaml is None:
        return None

    svc_meta = svc_yaml.get("metadata", {})
    svc = {
        "name": svc_meta.get("name", svc_dir.name),
        "description": svc_meta.get("description"),
        "functions": [],
    }

    funcs_dir = svc_dir / "functions"
    if funcs_dir.is_dir():
        for func_dir in sorted(funcs_dir.iterdir()):
            if not func_dir.is_dir():
                continue
            func = _parse_function(func_dir, errors)
            if func:
                svc["functions"].append(func)

    return svc


def _parse_function(func_dir: Path, errors: list[str]) -> dict[str, Any] | None:
    func_yaml_path = func_dir / "function.yaml"
    if not func_yaml_path.exists():
        errors.append(f"Missing function.yaml in {func_dir.name}")
        return None

    func_yaml = _load_yaml(func_yaml_path, errors)
    if func_yaml is None:
        return None

    metadata = func_yaml.get("metadata", {})
    spec = func_yaml.get("spec", {})
    env = spec.get("env", {})
    language = spec.get("language", "python")
    ext = "ts" if language == "typescript" else "py"
    handler_path = func_dir / f"handler.{ext}"

    code = None
    if handler_path.exists():
        try:
            code = handler_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"handler.{ext} in {func_dir.name} contains non-UTF8 content")
            return None

    return {
        "name": metadata.get("name", func_dir.name),
        "description": metadata.get("description"),
        "backend": spec.get("backend", "code_sandbox"),
        "language": language,
        "code": code,
        "requirements": spec.get("requirements") or [],
        "tags": spec.get("tags") or [],
        "public_safe": spec.get("public_safe", False),
        "locked": spec.get("locked", False),
        "input_schema": spec.get("input_schema"),
        "output_schema": spec.get("output_schema"),
        "required_env": env.get("required") or [],
        "optional_env": env.get("optional") or [],
    }


def _parse_agents(agents_dir: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not agents_dir.is_dir():
        return []

    agents = []
    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_yaml_path = agent_dir / "agent.yaml"
        if not agent_yaml_path.exists():
            errors.append(f"Missing agent.yaml in agents/{agent_dir.name}")
            continue

        agent_yaml = _load_yaml(agent_yaml_path, errors)
        if agent_yaml is None:
            continue

        metadata = agent_yaml.get("metadata", {})
        spec = agent_yaml.get("spec", {})
        heartbeat = spec.get("heartbeat", {})

        agents.append(
            {
                "name": metadata.get("name", agent_dir.name),
                "display_name": metadata.get("display_name"),
                "ai_engine": spec.get("ai_engine"),
                "ai_model": spec.get("ai_model"),
                "system_prompt": spec.get("system_prompt"),
                "tool_tier": spec.get("tool_tier", "standard"),
                "scheduled_tool_tier": spec.get("scheduled_tool_tier", "execute_only"),
                "auto_channel": spec.get("auto_channel"),
                "memory_limit_mb": spec.get("memory_limit_mb", 256),
                "cpu_limit": spec.get("cpu_limit", 0.25),
                "heartbeat_enabled": heartbeat.get("enabled", False),
                "heartbeat_interval": heartbeat.get("interval"),
                "orchestration_limits": spec.get("orchestration_limits"),
                "mcp_servers": spec.get("mcp_servers"),
                "schedules": spec.get("schedules") or [],
                "webhooks": spec.get("webhooks") or [],
                "channels": [{"channel_type": c.get("type")} for c in (spec.get("channels") or [])],
            }
        )

    return agents


def _load_yaml(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            errors.append(f"{path.name} is not a valid YAML mapping")
            return None
        return data
    except yaml.YAMLError as e:
        errors.append(f"Invalid YAML in {path.name}: {e}")
        return None
    except UnicodeDecodeError:
        errors.append(f"{path.name} contains non-UTF8 content")
        return None
