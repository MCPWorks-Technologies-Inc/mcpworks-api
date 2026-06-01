# Trust Scoring & OWASP Compliance - Specification

**Version:** 2.0.0
**Created:** 2026-04-08
**Status:** Implemented
**Spec Author:** Simon Carr
**Reviewers:** --

---

## History

v1.0 of this spec was titled "Agent Governance Toolkit Integration" and described
integrating a fabricated "Microsoft Agent Governance Toolkit" (`agent-os-kernel`,
`agent-compliance`). Those packages do not exist. The spec was written based on
hallucinated web search results.

v2.0 strips all fabricated external references and describes only the native
features that were actually implemented: trust scoring, OWASP compliance
evaluation, and trust-gated access control. No external dependencies are involved.

---

## 1. Overview

### 1.1 Purpose

Add native trust scoring and OWASP Agentic Top 10 compliance evaluation to
MCPWorks. These features give namespace owners dynamic agent capability
restriction based on behavior and a compliance posture report against industry
standards.

### 1.2 User Value

- **Trust scoring**: Agents that trigger security events (prompt injection,
  secret leaks) automatically lose trust and get restricted from sensitive
  functions. Recovery happens gradually through clean executions.
- **OWASP compliance**: Enterprise customers can pull a compliance report
  showing how their namespace configuration maps to the OWASP Agentic AI
  Top 10 risks, with grades and remediation guidance.

### 1.3 Success Criteria

- [x] `trust_score` column on agents table (0-1000, default 500)
- [x] Trust degrades on `fire_security_event`, recovers on clean execution
- [x] `check_function_access` gates on `min_trust_score` in access rules
- [x] Admin can set trust score via `configure_agent_access`
- [x] `GET /v1/namespaces/{ns}/compliance` returns graded OWASP report
- [x] All features are native (no external dependencies)

---

## 2. Implementation

### 2.1 Trust Scoring

**Files:**
- `src/mcpworks_api/models/agent.py` — `trust_score` (int, default 500), `trust_score_updated_at`
- `src/mcpworks_api/services/trust_score.py` — `adjust_trust_score()`, `recover_trust_score()`, `get_delta_for_event()`
- `src/mcpworks_api/core/agent_access.py` — `min_trust_score` gate in `check_function_access()`
- `src/mcpworks_api/services/security_event.py` — trust degradation on security events
- `src/mcpworks_api/mcp/run_handler.py` — trust recovery on successful execution
- `src/mcpworks_api/mcp/create_handler.py` — `configure_agent_access(trust_score=N)`
- `alembic/versions/20260409_000001_add_agent_trust_score.py`

**How it works:**
- Score range: 0 (quarantined) to 1000, default 500
- Security events decrement score (e.g., prompt injection: -50)
- Successful executions increment score by +1, capped at recovery ceiling (500)
- `check_function_access()` compares agent trust_score against rule's `min_trust_score`
- All updates are atomic SQL: `GREATEST(0, LEAST(1000, trust_score + delta))`

### 2.2 OWASP Compliance Endpoint

**Files:**
- `src/mcpworks_api/api/v1/compliance.py` — `GET /v1/namespaces/{ns}/compliance`
- `src/mcpworks_api/services/compliance.py` — `evaluate_compliance()`

**How it works:**
- Evaluates namespace configuration against 10 OWASP Agentic AI risks
- Checks: scanner pipeline, access rules, sandbox config, auth, rate limiting, trust scoring
- Returns per-risk coverage (covered/not), overall grade (A-F), remediation suggestions
- Pure logic — no external dependencies, no database writes

### 2.3 Trust-Gated Access Control

**Files:**
- `src/mcpworks_api/core/agent_access.py` — extended `check_function_access()`
- `src/mcpworks_api/mcp/tool_registry.py` — `min_trust_score` in access rule schema

**How it works:**
- Access rules can include `min_trust_score` on `allow_functions` rules
- When agent calls a function, its current trust_score is compared to the rule threshold
- Below threshold: blocked with `trust_score_gate` rule type in denial reason

---

## 3. Database Changes

**Migration:** `20260409_000001_add_agent_trust_score`

| Column | Type | Default | Constraint |
|--------|------|---------|------------|
| `agents.trust_score` | integer | 500 | CHECK (0 <= trust_score <= 1000) |
| `agents.trust_score_updated_at` | timestamp | NULL | |

---

## 4. Tests

- `tests/unit/test_trust_score.py` — trust score constants, delta mapping, boundary conditions
- `tests/unit/test_agent_access_trust.py` — trust gate in access control rules
- `tests/unit/test_compliance.py` — OWASP evaluation logic, grading, remediation

---

## Changelog

**v2.0.0 (2026-04-08):**
- Rewrote spec: removed all fabricated "Microsoft Agent Governance Toolkit" references
- Describes only native implementations: trust scoring, OWASP compliance, trust-gated access

**v1.1.0 (2026-04-08):**
- Removed agent_os_scanner (external toolkit was fabricated)

**v1.0.0 (2026-04-08):**
- Initial implementation (included fabricated Agent OS scanner references)

**v0.1.0 (2026-04-08):**
- Initial draft (based on hallucinated web search results)
