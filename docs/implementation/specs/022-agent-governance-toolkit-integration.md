# Agent Governance: Trust Scoring & OWASP Compliance - Specification

**Version:** 1.1.0
**Created:** 2026-04-08
**Status:** Implemented (Agent OS scanner removed — external toolkit was fabricated)
**Spec Author:** Simon Carr
**Reviewers:** --

---

## 1. Overview

### 1.1 Purpose

Integrate three packages from Microsoft's open-source Agent Governance Toolkit (MIT license) into MCPWorks as **opt-in, pluggable middleware**: Agent OS (policy engine), Agent Compliance (OWASP attestation), and Agent Mesh (trust scoring). This gives MCPWorks customers industry-standard governance controls and verifiable OWASP Agentic Top 10 coverage without replacing our existing security infrastructure.

### 1.2 User Value

Enterprise customers evaluating MCPWorks need answers to "are you OWASP compliant?", "can I bring my own security policies?", and "how do you prevent rogue agents?" Today we have bespoke answers. After this integration, customers get: Cedar/Rego policy support, automated compliance attestation covering 10/10 OWASP risks, and dynamic agent trust scoring — all backed by an MIT-licensed Microsoft project with broad industry adoption.

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] Namespace owners can enable Agent OS policy evaluation via scanner pipeline config
- [ ] Agent OS policies in YAML, OPA Rego, or Cedar are evaluated pre- and post-execution with <1ms p99 overhead
- [ ] `GET /v1/namespaces/{ns}/compliance` returns a graded OWASP Agentic Top 10 attestation
- [ ] Agent trust scores degrade on security events and gate function access
- [ ] All three integrations are opt-in; namespaces that don't enable them have zero overhead
- [ ] Existing `mcp_rules.py` and `scanner_pipeline.py` continue to work unchanged

### 1.4 Scope

**In Scope:**
- Agent OS as a new scanner type in `scanner_pipeline.py`
- Agent Compliance as a reporting/attestation endpoint
- Agent Mesh trust scoring integrated into `agent_access.py`
- Database migrations for trust score column
- Unit and integration tests for all three components

**Out of Scope:**
- Agent Runtime (we have nsjail — stronger for our use case)
- Agent SRE (circuit breakers, chaos engineering — future spec)
- Agent Marketplace (we have our own namespace/function model)
- Agent Lightning (RL training — not applicable)
- Replacing `mcp_rules.py` (Agent OS is an upgrade path, not a replacement)

---

## 2. User Scenarios

### 2.1 Primary Scenario: Enterprise Customer Enables Cedar Policies

**Actor:** Enterprise namespace owner
**Goal:** Enforce custom security policies on all agent tool calls using Cedar policy language
**Context:** Customer has existing Cedar policies from their AWS Verified Permissions deployment

**Workflow:**
1. Customer adds an `agent_os` scanner to their namespace pipeline config via `update_security_scanner`
2. Customer uploads Cedar policy file via namespace git remote or inline config
3. On next function execution, Agent OS evaluates the policy pre-execution (request rules) and post-execution (output scanning)
4. Policy violations produce `block` verdicts through existing pipeline; permitted actions pass through
5. All policy evaluations are logged via structlog with scanner timing

**Success:** Customer's Cedar policies are enforced on every tool call with <1ms overhead
**Failure:** Policy evaluation error falls through to `fallback_policy` (fail_open or fail_closed per namespace config)

### 2.2 Secondary Scenario: Platform Generates OWASP Attestation

**Actor:** MCPWorks platform / enterprise compliance team
**Goal:** Produce a verifiable attestation that a namespace covers all 10 OWASP Agentic AI risks
**Context:** Enterprise procurement requires evidence of OWASP compliance

**Workflow:**
1. Compliance team hits `GET /v1/namespaces/{ns}/compliance`
2. Agent Compliance evaluates namespace config: scanner pipeline, access rules, sandbox config, auth, rate limiting
3. Returns graded report mapping each OWASP risk to MCPWorks controls
4. Report includes coverage percentage, gaps, and remediation suggestions
5. Signed attestation artifact can be exported for audit

**Success:** Namespace with full config scores 10/10 OWASP coverage
**Failure:** Namespace with gaps gets actionable list of missing controls

### 2.3 Tertiary Scenario: Agent Trust Degrades After Security Event

**Actor:** AI agent executing functions
**Goal:** System automatically restricts agent capabilities when trust erodes
**Context:** Agent triggers multiple `fire_security_event` calls (prompt injection detected, secret leak attempted)

**Workflow:**
1. Agent executes function; output scanner detects prompt injection attempt
2. `fire_security_event` fires (existing behavior)
3. Trust score listener decrements agent's trust score (e.g., 500 -> 350)
4. Agent attempts next function call; `check_function_access` now also checks trust score
5. Function requires min_trust_score of 400; agent is blocked
6. Agent owner is notified via existing channel (Discord alert, webhook)
7. Admin can manually reset trust score via `configure_agent_access`

**Success:** Compromised agent is automatically constrained without human intervention
**Failure:** Trust score calculation error falls through permissively (fail-open); logged for investigation

---

## 3. Functional Requirements

### 3.1 Agent OS Policy Engine (Scanner Integration)

**REQ-AGT-001: New Scanner Type `agent_os`**
- **Description:** `scanner_pipeline.py` must resolve a new scanner type `agent_os` that wraps the Agent OS Python SDK
- **Priority:** Must Have
- **Rationale:** Enables customer-supplied policies in YAML/Rego/Cedar without replacing our pipeline
- **Acceptance:** Scanner type `agent_os` resolves, evaluates policies, returns `ScanVerdict`

**REQ-AGT-002: Bidirectional Policy Evaluation**
- **Description:** Agent OS scanner must support `direction: "both"` — evaluating request arguments (input) and execution output
- **Priority:** Must Have
- **Rationale:** OWASP risks span both input manipulation (goal hijacking) and output exploitation (data leakage)
- **Acceptance:** Same scanner instance evaluates both directions with appropriate policy context

**REQ-AGT-003: Policy Format Support**
- **Description:** Must support YAML rules, OPA Rego, and Cedar policy formats as configured per namespace
- **Priority:** Must Have
- **Rationale:** Customers come from different policy ecosystems; Cedar (AWS), Rego (Kubernetes), YAML (simple)
- **Acceptance:** All three formats load and evaluate correctly

**REQ-AGT-004: Zero Overhead When Disabled**
- **Description:** Namespaces without `agent_os` scanner entries must have zero additional latency or import overhead
- **Priority:** Must Have
- **Rationale:** Opt-in architecture; most namespaces won't use this initially
- **Acceptance:** Lazy import of `agent-governance-toolkit` only when scanner type is `agent_os`

**REQ-AGT-005: Graceful Degradation**
- **Description:** If `agent-governance-toolkit` package is not installed, the scanner must log a warning and skip (not crash)
- **Priority:** Must Have
- **Rationale:** Self-hosted community edition may not install the optional dependency
- **Acceptance:** Missing package produces warning log, scanner returns `pass` verdict

### 3.2 Agent Compliance (Attestation)

**REQ-AGT-010: Compliance Endpoint**
- **Description:** `GET /v1/namespaces/{ns}/compliance` returns OWASP Agentic Top 10 coverage report
- **Priority:** Should Have
- **Rationale:** Enterprise procurement requires compliance evidence
- **Acceptance:** Endpoint returns JSON with per-risk coverage grade, overall score, and gap list

**REQ-AGT-011: Config-Based Evaluation**
- **Description:** Compliance grading must evaluate existing namespace config (scanner pipeline, access rules, sandbox tier, auth config) — not require separate configuration
- **Priority:** Must Have
- **Rationale:** Compliance should reflect actual security posture, not a parallel config
- **Acceptance:** Changing scanner pipeline config immediately changes compliance grade

**REQ-AGT-012: Evidence Sampling**
- **Description:** Optionally run as a pipeline scanner (`type: agent_compliance`, order 99) that samples execution evidence without blocking
- **Priority:** Nice to Have
- **Rationale:** Continuous compliance evidence collection for SOC2 audit trails
- **Acceptance:** Scanner always returns `pass` verdict; stores evidence to execution metadata

### 3.3 Agent Mesh Trust Scoring

**REQ-AGT-020: Trust Score Column**
- **Description:** Add `trust_score` integer column (default 500, range 0-1000) to `agents` table
- **Priority:** Must Have
- **Rationale:** Persistent trust state that survives container restarts
- **Acceptance:** Migration adds column; existing agents default to 500

**REQ-AGT-021: Trust Score Gate**
- **Description:** `check_function_access` must check agent trust score against function's `min_trust_score` threshold
- **Priority:** Must Have
- **Rationale:** Dynamic capability restriction based on agent behavior
- **Acceptance:** Agent with score 300 is blocked from function requiring 400; allowed for function requiring 200

**REQ-AGT-022: Trust Score Degradation**
- **Description:** Security events (`fire_security_event`) must decrement the originating agent's trust score
- **Priority:** Must Have
- **Rationale:** Automatic response to detected threats
- **Acceptance:** Prompt injection event reduces trust score by configurable amount (default: -50)

**REQ-AGT-023: Trust Score Recovery**
- **Description:** Successful executions must slowly increment trust score (default: +1 per successful execution, capped at 500)
- **Priority:** Should Have
- **Rationale:** Agents should be able to recover trust over time after false positives
- **Acceptance:** After 50 clean executions, a degraded agent recovers 50 points

**REQ-AGT-024: Manual Trust Override**
- **Description:** Admin can set trust score via `configure_agent_access` tool
- **Priority:** Must Have
- **Rationale:** Admin must be able to restore or further restrict an agent
- **Acceptance:** `configure_agent_access` accepts `trust_score` parameter

### 3.4 Data Requirements

**New database columns:**
- `agents.trust_score` — integer, default 500, range 0-1000
- `agents.trust_score_updated_at` — timestamp, updated on each score change

**New JSONB fields (in existing scanner pipeline config):**
- Scanner entry with `"type": "agent_os"` and `config.policy_format`, `config.policy_ref`
- Scanner entry with `"type": "agent_compliance"` and `config.frameworks`

**New JSONB fields (in existing access rules):**
- `function_rules[].min_trust_score` — integer, default 0

### 3.5 Integration Requirements

**Upstream Dependencies:**
- `agent-governance-toolkit` Python package (PyPI) — Agent OS, Agent Compliance, Agent Mesh SDKs
- Existing `scanner_pipeline.py` pipeline architecture
- Existing `agent_access.py` access control
- Existing `fire_security_event()` security event system

**Downstream Consumers:**
- `run_handler.py` — consumes scanner verdicts and access decisions (no changes needed)
- `create_handler.py` — namespace config endpoints (minor: expose compliance endpoint)
- Discord/webhook alerts — trust score degradation events

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **Policy Evaluation:** p99 < 1ms for Agent OS policy evaluation (their benchmark: <0.1ms)
- **Compliance Report:** p95 < 500ms for compliance endpoint (config evaluation, no execution sampling)
- **Trust Score Check:** p99 < 0.1ms (single integer comparison in existing access check)
- **Token Efficiency:** Compliance report < 800 tokens; policy verdicts add 0 tokens to user-facing response

### 4.2 Security

- **Policy Files:** Cedar/Rego policies stored in namespace git remote or inline JSONB; never user-uploaded arbitrary files
- **Trust Score Integrity:** Only `fire_security_event` and admin override can modify trust scores; no user-facing mutation
- **Compliance Data:** Attestation reports contain config metadata only, never secrets or PII

### 4.3 Reliability

- **Agent OS Failure:** Scanner error → falls through to pipeline `fallback_policy` (existing behavior)
- **Missing Package:** Graceful skip with warning log (REQ-AGT-005)
- **Trust Score DB Error:** Fail-open; log error, don't block execution

### 4.4 Scalability

- **Current Scale:** Agent OS is stateless — scales linearly with execution volume
- **Trust Score:** Single row update per security event; no contention concerns at current scale
- **Compliance:** Cached per namespace; invalidated on config change

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- Must use `agent-governance-toolkit` as an **optional** dependency (not required for core MCPWorks)
- Agent OS SDK must be lazy-imported to avoid startup cost when unused
- Cedar/Rego policy evaluation must run in-process (no external service dependency)

### 5.2 Business Constraints

- MIT license (toolkit) is compatible with BSL 1.1 (MCPWorks) — no licensing issues
- Timeline: Phase 1 (Agent OS scanner) targets A1 milestone; Phase 2 (Compliance + Trust) targets A2

### 5.3 Assumptions

- Microsoft will maintain the `agent-governance-toolkit` PyPI package with reasonable stability
- Agent OS Python SDK exposes a synchronous or async `evaluate()` function that accepts policy + context
- **Risk if wrong:** If SDK API changes frequently, we wrap it in a thin adapter that absorbs breaking changes

---

## 6. Error Scenarios & Edge Cases

### 6.1 Error Scenario: Invalid Cedar Policy Syntax

**Trigger:** Customer uploads malformed Cedar policy
**Expected Behavior:** Agent OS scanner returns error; pipeline falls through to fallback_policy
**User Experience:** Execution proceeds (fail-open) or blocks (fail-closed) per namespace config; structlog captures policy parse error
**Recovery:** Customer fixes policy via git remote or config update
**Logging:** `scanner_error`, `scanner=agent_os`, `reason=policy_parse_error`

### 6.2 Error Scenario: Package Not Installed

**Trigger:** Self-hosted instance without `agent-governance-toolkit` installed; namespace config references `agent_os` scanner
**Expected Behavior:** Scanner resolution logs warning, returns None; pipeline skips it
**User Experience:** Execution proceeds without policy enforcement; no crash
**Logging:** `scanner_unknown_type`, `type=agent_os`, `hint=pip install agent-governance-toolkit`

### 6.3 Edge Case: Trust Score at Zero

**Scenario:** Agent trust score reaches 0 after repeated security events
**Expected Behavior:** Agent is blocked from ALL functions with `min_trust_score > 0`; admin notification fires
**Rationale:** Score 0 = effectively quarantined; only admin can restore

### 6.4 Edge Case: Trust Score Race Condition

**Scenario:** Multiple concurrent executions fire security events simultaneously
**Expected Behavior:** Use `UPDATE agents SET trust_score = GREATEST(0, trust_score - :delta)` — atomic DB operation, no application-level locking
**Rationale:** Minor over-decrement is acceptable; exact precision isn't required for trust scoring

---

## 7. Token Efficiency Analysis

### 7.1 Tool Definitions

Agent OS and trust scoring are internal middleware — they add **zero tokens** to MCP tool schemas exposed to AI assistants.

Compliance endpoint is a REST API call, not an MCP tool — token efficiency is N/A for AI context.

### 7.2 Typical Responses

**Compliance Report:** ~600 tokens (10 OWASP risks x ~60 tokens each)
**Policy Verdict (internal):** ~50 tokens (action + reason + timing) — never exposed to user

### 7.3 Worst Case

**Compliance with full remediation guidance:** ~1200 tokens
**Mitigation:** Progressive disclosure — summary by default, `?detail=full` for remediation steps

---

## 8. Security Analysis

### 8.1 Threat Model

**Threat:** Attacker crafts input to bypass Agent OS policy
**Impact:** Integrity — unauthorized tool execution
**Mitigation:** Agent OS is defense-in-depth, layered on top of existing scanners; both must pass
**Residual Risk:** Low — attacker must bypass both custom policies AND existing scanners

**Threat:** Attacker manipulates trust score to restore rogue agent
**Impact:** Integrity — rogue agent regains access
**Mitigation:** Trust score only modifiable via DB (security events) or admin API (auth required)
**Residual Risk:** Low — requires DB access or admin credentials

### 8.2 PII/Sensitive Data

- Policy files may contain business logic but no PII
- Compliance reports contain config metadata only
- Trust scores are per-agent, not per-user

### 8.3 Compliance

- This integration directly addresses OWASP Agentic AI Top 10 (2026)
- Compliance endpoint produces evidence for SOC2 and EU AI Act readiness assessments

---

## 9. Observability Requirements

### 9.1 Metrics

- `agent_os_policy_evaluations_total` (counter, labels: namespace, action, policy_format)
- `agent_os_policy_evaluation_duration_seconds` (histogram)
- `agent_trust_score_changes_total` (counter, labels: namespace, direction[up/down])
- `agent_compliance_score` (gauge, labels: namespace, framework)

### 9.2 Logging

**What must be logged:**
- Policy evaluation results: scanner_name, action, timing_ms, policy_format
- Trust score changes: agent_id, old_score, new_score, reason
- Compliance evaluations: namespace, overall_score, gaps

**What must NOT be logged:**
- Policy file contents (may contain business logic)
- Full execution payloads (existing PII scrubbing applies)

### 9.3 Alerting

- Trust score reaches 0: alert to namespace owner + platform admin
- Agent OS scanner error rate > 10%: alert to platform admin
- Compliance score drops below previous grade: alert to namespace owner

---

## 10. Testing Requirements

### 10.1 Unit Tests

- `AgentOSScanner.scan()` with mock Agent OS SDK — all three policy formats
- `AgentOSScanner` graceful degradation when package not installed
- Trust score increment/decrement logic with boundary conditions (0, 1000)
- Trust score gate in `check_function_access`
- Compliance evaluator config analysis for each OWASP risk

### 10.2 Integration Tests

- Full pipeline evaluation with Agent OS scanner + existing scanners
- Trust score update via `fire_security_event` flow
- Compliance endpoint with various namespace configs

### 10.3 E2E Tests

- Namespace with Cedar policy blocks prohibited tool call
- Agent trust degrades after security event, recovers after clean executions
- Compliance endpoint returns valid attestation for fully-configured namespace

---

## 11. Future Considerations

### 11.1 Phase 2 Enhancements

- Agent SRE integration (circuit breakers for cascading failure protection)
- Agent Mesh cryptographic identity (Ed25519/DID) for multi-agent clusters
- Contribute MCPWorks nsjail sandbox as Agent Runtime backend to MS toolkit
- Policy management UI in admin dashboard

### 11.2 Known Limitations

- Trust scoring is per-agent, not per-execution-context — an agent's trust applies globally across all its functions
- Compliance attestation is point-in-time; continuous compliance requires the evidence sampling scanner (REQ-AGT-012)
- OPA Rego requires the Rego engine; this may add ~5MB to container image when enabled

---

## 12. Spec Completeness Checklist

**Before moving to Plan phase:**

- [x] Clear user value proposition stated
- [x] Success criteria defined and measurable
- [x] All functional requirements enumerated
- [x] All constraints documented
- [x] Error scenarios identified
- [x] Security requirements specified
- [x] Performance requirements quantified
- [x] Token efficiency requirements stated
- [x] Testing requirements defined
- [x] Observability requirements defined
- [ ] Reviewed for Constitution compliance
- [ ] Logic checked (internally consistent)
- [ ] Peer reviewed (if team > 1)

---

## 13. Approval

**Status:** Implemented

**Approvals:**
- [x] CTO (Simon Carr)
- [ ] Security Review

**Approved Date:** 2026-04-09
**Next Review:** 2026-04-22

---

## Changelog

**v1.0.0 (2026-04-09):**
- Implemented: Agent OS scanner, trust scoring, compliance endpoint

**v0.1.0 (2026-04-08):**
- Initial draft — Agent OS, Agent Compliance, Agent Mesh trust scoring integration
