"""MCP server rule evaluation engine.

Evaluates per-server request and response rules inline in the proxy path.
Tool matching uses fnmatch for glob support.
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class RuleBlockError(Exception):
    def __init__(self, tool: str, rule_id: str) -> None:
        self.tool = tool
        self.rule_id = rule_id
        super().__init__(f"Tool '{tool}' blocked by namespace rule (rule_id: {rule_id})")


def evaluate_request_rules(
    rules: list[dict[str, Any]],
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    for rule in rules:
        tool_pattern = rule.get("tool", "*")
        if not fnmatch(tool_name, tool_pattern):
            continue

        rule_type = rule.get("type")
        rule_id = rule.get("id", "unknown")

        if rule_type == "block_tool":
            raise RuleBlockError(tool_name, rule_id)

        elif rule_type == "inject_param":
            key = rule.get("key")
            if key:
                if "value" in rule:
                    arguments[key] = rule["value"]
                elif "prepend" in rule and key in arguments:
                    arguments[key] = rule["prepend"] + str(arguments[key])
                elif "append" in rule and key in arguments:
                    arguments[key] = str(arguments[key]) + rule["append"]
                elif "prepend" in rule:
                    arguments[key] = rule["prepend"]

        elif rule_type == "require_param":
            key = rule.get("key")
            if key and key not in arguments:
                raise ValueError(
                    f"Parameter '{key}' required for tool '{tool_name}' (rule_id: {rule_id})"
                )

        elif rule_type == "cap_param":
            key = rule.get("key")
            max_val = rule.get("max")
            if key and max_val is not None and key in arguments:
                try:
                    if float(arguments[key]) > float(max_val):
                        arguments[key] = max_val
                except (ValueError, TypeError):
                    pass

    return arguments


def evaluate_response_rules(
    rules: list[dict[str, Any]],
    tool_name: str,
    response_text: str,
    server_name: str,
    settings: dict[str, Any] | None = None,
) -> str:
    from mcpworks_api.core.trust_boundary import (
        apply_injection_flags,
        redact_injection,
        wrap_mcp_response,
    )
    from mcpworks_api.sandbox.injection_scan import scan_for_injections

    injections_found = 0
    output = response_text

    for rule in rules:
        tools_pattern = rule.get("tools", "*")
        if isinstance(tools_pattern, list):
            if not any(fnmatch(tool_name, p) for p in tools_pattern):
                continue
        elif not fnmatch(tool_name, tools_pattern):
            continue

        rule_type = rule.get("type")

        if rule_type == "scan_injection":
            strictness = rule.get("strictness", "warn")
            matches = scan_for_injections(output)
            injections_found = len(matches)
            if matches:
                logger.info(
                    "rule_injection_scan",
                    server=server_name,
                    tool=tool_name,
                    strictness=strictness,
                    count=injections_found,
                )
                if strictness == "flag":
                    output = apply_injection_flags(output, matches)
                elif strictness == "block":
                    output = redact_injection(output, matches)

        elif rule_type == "wrap_trust_boundary":
            tool_trust_overrides = (settings or {}).get("tool_trust_overrides", {})
            tool_trust = tool_trust_overrides.get(tool_name, "data")
            if tool_trust != "prompt":
                output = wrap_mcp_response(output, server_name, tool_name, injections_found)

        elif rule_type == "strip_html":
            output = re.sub(r"<[^>]+>", "", output)

        elif rule_type == "inject_header":
            header_text = rule.get("text", "")
            if header_text:
                output = header_text + "\n" + output

        elif rule_type == "redact_fields":
            fields = rule.get("fields", [])
            if fields:
                import json

                try:
                    data = json.loads(output)
                    for field_path in fields:
                        _redact_field(data, field_path.split("."))
                    output = json.dumps(data)
                except (json.JSONDecodeError, ValueError):
                    pass

    return output


def _redact_field(data: dict | list, path: list[str]) -> None:
    if not path or not isinstance(data, dict):
        return
    key = path[0]
    if len(path) == 1:
        data.pop(key, None)
    elif key in data:
        _redact_field(data[key], path[1:])
