"""Per-agent access control evaluation engine.

Evaluates function and state access rules for agents using fnmatch glob patterns.
Deny rules always take precedence over allow rules.
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AgentAccessDeniedError(Exception):
    def __init__(
        self, agent: str, resource: str, rule_id: str, resource_type: str = "function"
    ) -> None:
        self.agent = agent
        self.resource = resource
        self.rule_id = rule_id
        self.resource_type = resource_type
        super().__init__(
            f"Agent '{agent}' is not permitted to access {resource_type} "
            f"'{resource}' (rule: {rule_id})"
        )


def check_function_access(
    access_rules: dict[str, Any] | None,
    service_name: str,
    function_name: str,
    trust_score: int | None = None,
) -> tuple[bool, str | None]:
    """Check if an agent is allowed to call a function.

    Returns (allowed, blocking_rule_id).
    When trust_score is provided, also checks min_trust_score on matching allow rules.
    """
    if not access_rules:
        return True, None

    function_rules = access_rules.get("function_rules", [])
    if not function_rules:
        return True, None

    qualified = f"{service_name}.{function_name}"

    deny_service_rules = [r for r in function_rules if r.get("type") == "deny_services"]
    deny_function_rules = [r for r in function_rules if r.get("type") == "deny_functions"]
    allow_service_rules = [r for r in function_rules if r.get("type") == "allow_services"]
    allow_function_rules = [r for r in function_rules if r.get("type") == "allow_functions"]

    for rule in deny_service_rules:
        for pattern in rule.get("patterns", []):
            if fnmatch(service_name, pattern):
                logger.info(
                    "agent_access_denied",
                    service=service_name,
                    function=function_name,
                    rule_id=rule.get("id"),
                    rule_type="deny_services",
                )
                return False, rule.get("id")

    for rule in deny_function_rules:
        for pattern in rule.get("patterns", []):
            if fnmatch(qualified, pattern):
                logger.info(
                    "agent_access_denied",
                    function=qualified,
                    rule_id=rule.get("id"),
                    rule_type="deny_functions",
                )
                return False, rule.get("id")

    if allow_service_rules:
        service_allowed = False
        for rule in allow_service_rules:
            for pattern in rule.get("patterns", []):
                if fnmatch(service_name, pattern):
                    service_allowed = True
                    break
            if service_allowed:
                break
        if not service_allowed:
            rule_id = allow_service_rules[0].get("id") if allow_service_rules else None
            return False, rule_id

    if allow_function_rules:
        func_allowed = False
        matching_rule = None
        for rule in allow_function_rules:
            for pattern in rule.get("patterns", []):
                if fnmatch(qualified, pattern):
                    func_allowed = True
                    matching_rule = rule
                    break
            if func_allowed:
                break
        if not func_allowed:
            rule_id = allow_function_rules[0].get("id") if allow_function_rules else None
            return False, rule_id

        if trust_score is not None and matching_rule:
            min_trust = matching_rule.get("min_trust_score", 0)
            if trust_score < min_trust:
                logger.info(
                    "agent_access_denied",
                    function=qualified,
                    rule_id=matching_rule.get("id"),
                    rule_type="trust_score_gate",
                    trust_score=trust_score,
                    min_trust_score=min_trust,
                )
                return False, matching_rule.get("id")

    return True, None


def check_state_access(
    access_rules: dict[str, Any] | None,
    key: str,
) -> tuple[bool, str | None]:
    """Check if an agent is allowed to access a state key.

    Returns (allowed, blocking_rule_id).
    """
    if not access_rules:
        return True, None

    state_rules = access_rules.get("state_rules", [])
    if not state_rules:
        return True, None

    deny_rules = [r for r in state_rules if r.get("type") == "deny_keys"]
    allow_rules = [r for r in state_rules if r.get("type") == "allow_keys"]

    for rule in deny_rules:
        for pattern in rule.get("patterns", []):
            if fnmatch(key, pattern):
                logger.info(
                    "agent_state_access_denied",
                    key=key,
                    rule_id=rule.get("id"),
                    rule_type="deny_keys",
                )
                return False, rule.get("id")

    if allow_rules:
        key_allowed = False
        for rule in allow_rules:
            for pattern in rule.get("patterns", []):
                if fnmatch(key, pattern):
                    key_allowed = True
                    break
            if key_allowed:
                break
        if not key_allowed:
            rule_id = allow_rules[0].get("id") if allow_rules else None
            return False, rule_id

    return True, None


def filter_state_keys(
    access_rules: dict[str, Any] | None,
    keys: list[str],
) -> list[str]:
    """Filter a list of state keys to only those the agent can access."""
    if not access_rules:
        return keys
    return [k for k in keys if check_state_access(access_rules, k)[0]]
