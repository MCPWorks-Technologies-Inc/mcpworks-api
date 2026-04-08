"""OWASP Agentic Top 10 compliance evaluation service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

OWASP_RISKS = [
    {
        "id": "OWASP-AT-01",
        "name": "Agent Goal Hijack",
        "check": "input_scanner",
        "remediation": "Add a scanner with direction 'input' or 'both' (e.g., pattern_scanner or agent_os) to detect prompt injection.",
    },
    {
        "id": "OWASP-AT-02",
        "name": "Tool Misuse",
        "check": "access_rules",
        "remediation": "Configure agent access rules via configure_agent_access to restrict function access.",
    },
    {
        "id": "OWASP-AT-03",
        "name": "Identity & Privilege Abuse",
        "check": "auth_enabled",
        "remediation": "Ensure API key authentication is enabled for all namespace endpoints.",
    },
    {
        "id": "OWASP-AT-04",
        "name": "Supply Chain Vulnerabilities",
        "check": "sandbox_tier",
        "remediation": "Use 'builder' or higher sandbox tier with locked dependencies and pip audit in CI.",
    },
    {
        "id": "OWASP-AT-05",
        "name": "Unexpected Code Execution",
        "check": "sandbox_present",
        "remediation": "All functions execute in nsjail sandbox with seccomp allowlist by default.",
    },
    {
        "id": "OWASP-AT-06",
        "name": "Memory & Context Poisoning",
        "check": "output_scanner",
        "remediation": "Add trust_boundary scanner to output pipeline to enforce output_trust boundaries.",
    },
    {
        "id": "OWASP-AT-07",
        "name": "Insecure Inter-Agent Communication",
        "check": "namespace_isolation",
        "remediation": "Namespace isolation is enforced by default. No cross-namespace agent communication without explicit configuration.",
    },
    {
        "id": "OWASP-AT-08",
        "name": "Cascading Failures",
        "check": "rate_limit",
        "remediation": "Enable rate limiting on namespace endpoints to prevent cascading resource exhaustion.",
    },
    {
        "id": "OWASP-AT-09",
        "name": "Human-Agent Trust Exploitation",
        "check": "access_rules",
        "remediation": "Configure agent access rules to restrict sensitive operations and require human approval workflows.",
    },
    {
        "id": "OWASP-AT-10",
        "name": "Rogue Agents",
        "check": "trust_scoring",
        "remediation": "Enable trust scoring and set min_trust_score on sensitive function rules via configure_agent_access.",
    },
]


def _has_scanner_direction(pipeline: dict[str, Any] | None, direction: str) -> bool:
    if not pipeline:
        return False
    for s in pipeline.get("scanners", []):
        if not s.get("enabled", True):
            continue
        d = s.get("direction", "output")
        if d == direction or d == "both":
            return True
    return False


def _has_scanner_type(pipeline: dict[str, Any] | None, name: str) -> bool:
    if not pipeline:
        return False
    for s in pipeline.get("scanners", []):
        if not s.get("enabled", True):
            continue
        if s.get("name") == name or s.get("type") == name:
            return True
    return False


def _check_risk(
    risk: dict[str, Any],
    scanner_pipeline: dict[str, Any] | None,
    access_rules_exist: bool,
    sandbox_tier: str,
    auth_enabled: bool,
    rate_limit_enabled: bool,
    trust_scoring_enabled: bool,
) -> str:
    check = risk["check"]

    if check == "input_scanner":
        return "covered" if _has_scanner_direction(scanner_pipeline, "input") else "gap"

    if check == "access_rules":
        return "covered" if access_rules_exist else "gap"

    if check == "auth_enabled":
        return "covered" if auth_enabled else "gap"

    if check == "sandbox_tier":
        return "covered" if sandbox_tier in ("builder", "enterprise") else "partial"

    if check == "sandbox_present":
        return "covered"

    if check == "output_scanner":
        return "covered" if _has_scanner_type(scanner_pipeline, "trust_boundary") else "gap"

    if check == "namespace_isolation":
        return "covered"

    if check == "rate_limit":
        return "covered" if rate_limit_enabled else "gap"

    if check == "trust_scoring":
        return "covered" if trust_scoring_enabled else "gap"

    return "gap"


def _compute_grade(coverage_pct: int) -> str:
    if coverage_pct >= 90:
        return "A"
    if coverage_pct >= 80:
        return "B"
    if coverage_pct >= 70:
        return "C"
    if coverage_pct >= 60:
        return "D"
    return "F"


def _try_governance_verifier_grade(coverage_pct: int) -> str | None:  # noqa: ARG001
    try:
        from agent_compliance.verify import GovernanceVerifier

        verifier = GovernanceVerifier()
        attestation = verifier.verify()
        return attestation.compliance_grade()
    except Exception:
        return None


def evaluate_compliance(
    namespace: str,
    scanner_pipeline: dict[str, Any] | None,
    access_rules_exist: bool,
    sandbox_tier: str,
    auth_enabled: bool,
    rate_limit_enabled: bool,
    trust_scoring_enabled: bool,
    detail: str = "summary",
) -> dict[str, Any]:
    risks = []
    covered_count = 0

    for risk_def in OWASP_RISKS:
        status = _check_risk(
            risk_def,
            scanner_pipeline,
            access_rules_exist,
            sandbox_tier,
            auth_enabled,
            rate_limit_enabled,
            trust_scoring_enabled,
        )

        if status == "covered":
            covered_count += 1
        elif status == "partial":
            covered_count += 0.5

        entry: dict[str, Any] = {
            "id": risk_def["id"],
            "name": risk_def["name"],
            "status": status,
            "control": None if status == "gap" else risk_def["check"],
            "remediation": risk_def["remediation"]
            if (detail == "full" and status != "covered")
            else None,
        }
        risks.append(entry)

    coverage_pct = int((covered_count / len(OWASP_RISKS)) * 100)

    return {
        "namespace": namespace,
        "framework": "owasp-agentic-top-10",
        "grade": _compute_grade(coverage_pct),
        "coverage_pct": coverage_pct,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "risks": risks,
    }
