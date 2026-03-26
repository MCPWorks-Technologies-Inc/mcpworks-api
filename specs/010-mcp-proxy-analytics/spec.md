# MCP Proxy Analytics & AI Self-Optimization - Specification

**Version:** 0.1.0 (Draft)
**Created:** 2026-03-26
**Status:** Draft
**Spec Author:** Simon Carr
**Feature Branch:** `010-mcp-proxy-analytics`

---

## Clarifications

### Session 2026-03-26

- Q: Why Redis for analytics storage instead of PostgreSQL? → A: PostgreSQL. Redis is a cache and ephemeral — analytics data with 30-day retention, structured aggregation (GROUP BY, AVG, time bucketing), and joins to existing tables belongs in the relational DB. Async INSERT after proxy response, same perf profile as Redis ZADD. One migration, no Redis memory pressure.
- Q: How does suggest_optimizations know which fields to recommend redacting? → A: Live probe. When called, makes one real call per tool with minimal arguments to sample the current response structure. Analyzes JSON for large fields. No response content stored in analytics tables.
- Q: Should live probes be automatic or user-triggered? → A: User-triggered. suggest_optimizations accepts an optional `probe` parameter listing tool names to probe. No automatic probing — avoids side effects from write-like tools and gives the user control over which tools get real calls.
- Q: How should the 30-day cleanup job run? → A: APScheduler daily task inside the API process. Already use APScheduler for agent scheduling. No external cron dependency.
- Q: Should analytics tools be a new group or part of MCP_SERVER_TOOLS? → A: New ANALYTICS_TOOLS group. Read-only observability tools are conceptually different from server management. Separate group enables tier-based or feature-flag gating.

---

## 1. Overview

### 1.1 Purpose

Capture per-server, per-tool telemetry from the MCP proxy and expose it to the AI through MCP tools — enabling the AI to optimize its own token usage, tune server settings, and add rules based on real usage data.

### 1.2 User Value

Today, the AI has no visibility into how MCP server tools perform. It cannot know that `list_channels` returns 200KB on average, that `search_gmail` times out 15% of the time, or that 37 out of 40 Google Workspace tools are never called. The AI flies blind on infrastructure costs.

With proxy analytics, the AI can:
- See which tools consume the most tokens and add `redact_fields` rules to trim them
- Detect timeout-prone tools and increase their timeout settings
- Identify unused tools and recommend removing them from the wrapper package
- Report namespace-wide token savings (data processed in sandbox vs tokens returned to AI)
- Self-optimize over time by querying stats after each adjustment

This is the AI optimizing its own infrastructure costs based on real telemetry. The proxy is the moat — no direct MCP connection gives you this observability.

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] Every MCP proxy call records response size, latency, tool name, status, and error type
- [ ] Stats are queryable via MCP tools with configurable time periods (1h, 24h, 7d, 30d)
- [ ] The AI can call `get_mcp_server_stats` and get per-tool breakdowns
- [ ] The AI can call `get_token_savings_report` and get namespace-wide savings data
- [ ] The AI can call `suggest_optimizations` and get actionable recommendations it can apply via existing tools (set_mcp_server_setting, add_mcp_server_rule)

### 1.4 Scope

**In Scope:**
- Per-call telemetry capture in the MCP proxy (response size, latency, status, error type)
- Per-execution telemetry for sandbox runs (MCP calls made, total data processed, result size)
- Storage in PostgreSQL with periodic cleanup (30-day retention)
- 4 MCP tools for querying stats and getting optimization suggestions
- Prometheus metrics export for external monitoring
- Token estimation (response bytes / 4 as approximation)

**Out of Scope:**
- Historical analytics dashboard (console UI for graphs) — future spec
- Cost estimation in dollars (requires knowing the user's AI provider pricing) — future
- Automatic rule application (AI must explicitly call tools to make changes) — by design
- Per-function profiling inside the sandbox (sandbox is opaque) — architectural constraint
- Real-time streaming of stats (polling via MCP tools is sufficient)

---

## 2. User Scenarios

### 2.1 Primary Scenario: AI Optimizes Token-Heavy Tools

**Actor:** AI assistant managing a namespace with Google Workspace MCP
**Goal:** Reduce token consumption from MCP tool calls
**Context:** Namespace has been running for a week with regular function executions

**Workflow:**
1. User asks: "How are my MCP servers performing? Any optimization opportunities?"
2. AI calls `get_mcp_server_stats(name="google-workspace", period="7d")`
3. Stats show: `list_events` returns 450KB avg (est. 112,000 tokens), called 23 times/day
4. AI calls `suggest_optimizations(name="google-workspace")`
5. Suggestion: "Tool `list_events` averages 450KB response. Only `summary` and `start_time` fields are typically used. Add a `redact_fields` rule to strip `attendees`, `description`, `attachments`."
6. AI calls `add_mcp_server_rule` to add the redact rule
7. User sees the optimization applied

**Success:** Token usage for `list_events` drops from 112K to ~5K tokens per call.

### 2.2 Secondary Scenario: Namespace Token Savings Report

**Actor:** Developer reviewing AI agent costs
**Goal:** Understand how much MCPWorks is saving vs direct MCP connections
**Context:** Namespace runs daily agents that process emails and Slack messages

**Workflow:**
1. Developer asks: "Show me the token savings for this namespace"
2. AI calls `get_token_savings_report(period="30d")`
3. Report shows:
   - Total MCP data processed in sandbox: 2.4GB (est. 600M tokens)
   - Total data returned to AI context: 12MB (est. 3M tokens)
   - Savings: 99.5%
   - Top token consumers: `search_gmail` (800MB), `list_channels` (400MB)
4. Developer understands the ROI of the platform

### 2.3 Tertiary Scenario: AI Detects and Fixes Reliability Issues

**Actor:** AI agent with scheduled runs
**Goal:** Identify and fix timeout-prone MCP tools
**Context:** Agent's hourly runs occasionally fail

**Workflow:**
1. AI calls `get_mcp_server_stats(name="slack", period="24h")`
2. Stats show: `search_messages` has 22% error rate, 18% timeout rate
3. AI calls `set_mcp_server_setting(name="slack", key="timeout_seconds", value=60)`
4. AI calls `add_mcp_server_rule` to add `cap_param` limiting search results to 100
5. Next run succeeds consistently

---

## 3. Functional Requirements

### 3.1 Telemetry Capture

**REQ-TEL-001: Per-Call Metrics**
- **Description:** Every MCP proxy call records telemetry
- **Priority:** Must Have
- **Fields captured per call:**
  - `namespace_id` — which namespace
  - `server_name` — which MCP server
  - `tool_name` — which tool
  - `timestamp` — when the call was made
  - `latency_ms` — round-trip time to external MCP server
  - `response_bytes` — size of response before truncation
  - `response_tokens_est` — `response_bytes / 4` (approximation)
  - `status` — `success`, `timeout`, `error`, `blocked` (by rule)
  - `error_type` — null or error classification
  - `truncated` — whether response was truncated by limit
  - `injections_found` — count from injection scanner
- **Storage:** PostgreSQL table `mcp_proxy_calls`. Async INSERT after proxy response. 30-day retention via periodic cleanup.

**REQ-TEL-002: Per-Execution Metrics**
- **Description:** Each sandbox execution records MCP-related telemetry
- **Priority:** Should Have
- **Fields captured per execution:**
  - `namespace_id`
  - `execution_id`
  - `mcp_calls_count` — total MCP proxy calls made during this execution
  - `mcp_bytes_total` — total response bytes from all MCP calls
  - `result_bytes` — size of sandbox result returned to AI
  - `tokens_saved_est` — `(mcp_bytes_total - result_bytes) / 4`
- **Storage:** PostgreSQL table `mcp_execution_stats`. Async INSERT. 30-day retention.

### 3.2 MCP Tools

**REQ-TOOL-001: Get MCP Server Stats**
- **Description:** MCP tool `get_mcp_server_stats` returns per-tool performance breakdown
- **Priority:** Must Have
- **Parameters:** `name` (server), `period` (default `24h`, options: `1h`, `24h`, `7d`, `30d`)
- **Returns:**
  ```json
  {
    "server": "google-workspace",
    "period": "24h",
    "total_calls": 156,
    "total_errors": 12,
    "error_rate": 0.077,
    "tools": [
      {
        "name": "search_gmail_messages",
        "calls": 47,
        "avg_latency_ms": 340,
        "avg_response_bytes": 85000,
        "avg_response_tokens_est": 21250,
        "error_count": 3,
        "timeout_count": 2,
        "truncation_count": 0,
        "injections_detected": 1
      }
    ]
  }
  ```
- **Authorization:** Read access

**REQ-TOOL-002: Get Token Savings Report**
- **Description:** MCP tool `get_token_savings_report` returns namespace-wide savings data
- **Priority:** Must Have
- **Parameters:** `period` (default `24h`)
- **Returns:**
  ```json
  {
    "period": "24h",
    "mcp_data_processed_bytes": 12500000,
    "mcp_data_processed_tokens_est": 3125000,
    "result_returned_bytes": 45000,
    "result_returned_tokens_est": 11250,
    "savings_percent": 99.6,
    "top_consumers": [
      {"server": "google-workspace", "tool": "search_gmail", "bytes": 8500000}
    ]
  }
  ```
- **Authorization:** Read access

**REQ-TOOL-003: Suggest Optimizations**
- **Description:** MCP tool `suggest_optimizations` analyzes stats and returns actionable recommendations
- **Priority:** Should Have
- **Parameters:** `name` (server, optional — all servers if omitted), `probe` (optional list of tool names — makes a live call to sample response structure for field-level redact suggestions. Only probe tools you know are safe to call.)
- **Returns:** List of suggestions, each with a recommended action the AI can take via existing tools
  ```json
  {
    "suggestions": [
      {
        "type": "redact_fields",
        "server": "google-workspace",
        "tool": "list_events",
        "reason": "Avg response 450KB. Fields 'attendees', 'description' account for ~80%.",
        "action": "add_mcp_server_rule(name='google-workspace', direction='response', rule={'type': 'redact_fields', 'tools': ['list_events'], 'fields': ['attendees', 'description']})",
        "estimated_savings_percent": 80
      },
      {
        "type": "increase_timeout",
        "server": "slack",
        "tool": "search_messages",
        "reason": "18% timeout rate at current 30s. Avg latency 22s for successful calls.",
        "action": "set_mcp_server_setting(name='slack', key='timeout_seconds', value=60)",
        "estimated_impact": "Reduce timeout errors by ~90%"
      }
    ]
  }
  ```
- **Authorization:** Read access

**REQ-TOOL-004: Get Function MCP Stats**
- **Description:** MCP tool `get_function_mcp_stats` returns per-function MCP usage
- **Priority:** Should Have
- **Parameters:** `service`, `function`, `period` (default `24h`)
- **Returns:** MCP calls per execution, total bytes consumed, tokens saved
- **Authorization:** Read access

### 3.3 Optimization Suggestion Rules

**REQ-OPT-001: Suggestion Generation**
- **Description:** The `suggest_optimizations` tool analyzes collected stats and generates recommendations
- **Priority:** Should Have
- **Suggestion rules:**
  - **Large responses:** If avg response > 100KB, make a live probe call to the tool to sample the current response structure. Analyze top-level JSON keys by size, suggest `redact_fields` for the largest fields.
  - **High timeout rate:** If timeout rate > 10%, suggest increasing `timeout_seconds`
  - **High error rate:** If error rate > 20%, suggest checking credentials or server health
  - **Unused tools:** If tools have 0 calls over 7 days, suggest reviewing whether wrappers are needed
  - **Call cap proximity:** If avg calls per execution > 80% of `max_calls_per_execution`, suggest raising the cap
  - **Truncation frequency:** If truncation rate > 5%, suggest increasing `response_limit_bytes` or adding `redact_fields`

### 3.4 Prometheus Metrics

**REQ-PROM-001: Export Metrics**
- **Description:** Key proxy metrics exported via the existing `/metrics` Prometheus endpoint
- **Priority:** Should Have
- **Metrics:**
  - `mcpworks_mcp_proxy_calls_total` (counter) — labels: namespace, server, tool, status
  - `mcpworks_mcp_proxy_response_bytes` (histogram) — labels: namespace, server, tool
  - `mcpworks_mcp_proxy_latency_seconds` (histogram) — labels: namespace, server, tool
  - `mcpworks_mcp_proxy_injections_total` (counter) — labels: namespace, server
  - `mcpworks_mcp_token_savings_bytes` (counter) — labels: namespace (mcp_bytes - result_bytes)

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **Telemetry capture:** < 1ms overhead per proxy call (async INSERT, fire-and-forget)
- **Stats query:** < 200ms for aggregation over 24h window with proper indexes
- **No impact on proxy latency** — telemetry is fire-and-forget (asyncio.create_task after response returned)

### 4.2 Storage

- **PostgreSQL tables** with timestamp indexes for efficient range queries
- **30-day retention** — APScheduler daily task deletes rows older than 30 days (same scheduler infrastructure as agent cron jobs)
- **Estimated storage:** ~200 bytes per call record. At 1000 calls/day = ~6MB/month per namespace. Well within PostgreSQL comfort zone.
- **Async writes** — telemetry INSERT runs in a background task after the proxy response is returned, same pattern as security event logging

### 4.3 Reliability

- **Telemetry failures don't block proxy calls.** If the async INSERT fails, the call proceeds without stats.
- **Approximate accuracy is fine.** Token estimation is `bytes/4`. Aggregation may miss calls if async INSERT fails. This is operational intelligence, not billing.

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- PostgreSQL for analytics storage (two new tables: mcp_proxy_calls, mcp_execution_stats)
- Token estimation is approximate (`bytes / 4`) — good enough for optimization decisions
- Suggestion engine is rule-based, not LLM-based (no AI calls for generating suggestions)
- Per-function stats require the execution token registry to track which function made which proxy calls — may need enrichment from 008's exec token registry

### 5.2 Assumptions

- Users care about token costs and will act on optimization suggestions
- 30-day retention is sufficient for trend analysis
- The AI acting on suggestions (calling tools) is the right UX — no auto-optimization
- Prometheus metrics are consumed by the planned Grafana stack (infra/mgmt)

---

## 6. Error Scenarios & Edge Cases

### 6.1 Edge Case: No Stats Available

**Scenario:** User queries stats for a newly added server with 0 calls
**Expected Behavior:** Return empty stats with `total_calls: 0`. Suggestions return "Insufficient data."

### 6.2 Edge Case: DB Write Failure

**Scenario:** Async INSERT fails (connection issue, disk full)
**Expected Behavior:** Failure is logged. Proxy call result is unaffected. Stats for that call are lost — acceptable for operational intelligence.

### 6.3 Edge Case: Very High Call Volume

**Scenario:** Namespace makes 100K+ proxy calls per day
**Expected Behavior:** PostgreSQL handles this with indexed queries. Aggregation over 30d with proper indexes is fast. For very high volume, consider time-based partitioning in Phase 2.

---

## 7. Data Model

### 7.1 New Table: mcp_proxy_calls

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | |
| namespace_id | UUID | FK → namespaces.id, ON DELETE CASCADE | |
| server_name | VARCHAR(63) | NOT NULL | MCP server name |
| tool_name | VARCHAR(255) | NOT NULL | Tool called |
| called_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | When the call was made |
| latency_ms | INTEGER | NOT NULL | Round-trip time |
| response_bytes | INTEGER | NOT NULL | Response size before truncation |
| response_tokens_est | INTEGER | NOT NULL | response_bytes / 4 |
| status | VARCHAR(20) | NOT NULL | success, timeout, error, blocked |
| error_type | VARCHAR(100) | NULLABLE | Error classification |
| truncated | BOOLEAN | NOT NULL, DEFAULT false | Whether response hit limit |
| injections_found | INTEGER | NOT NULL, DEFAULT 0 | Injection scanner count |

**Indexes:**
- `(namespace_id, called_at)` — time-range queries per namespace
- `(namespace_id, server_name, tool_name, called_at)` — per-tool aggregation

**Retention:** Rows older than 30 days deleted by periodic cleanup task.

### 7.2 New Table: mcp_execution_stats

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | |
| namespace_id | UUID | FK → namespaces.id, ON DELETE CASCADE | |
| execution_id | VARCHAR(64) | NOT NULL | Sandbox execution ID |
| executed_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| mcp_calls_count | INTEGER | NOT NULL, DEFAULT 0 | Total MCP proxy calls |
| mcp_bytes_total | INTEGER | NOT NULL, DEFAULT 0 | Total response bytes from MCP |
| result_bytes | INTEGER | NOT NULL, DEFAULT 0 | Sandbox result size returned to AI |
| tokens_saved_est | INTEGER | NOT NULL, DEFAULT 0 | (mcp_bytes_total - result_bytes) / 4 |

**Indexes:**
- `(namespace_id, executed_at)` — time-range queries

**Retention:** Same 30-day cleanup.

---

## 8. Security Analysis

### 8.1 Data Sensitivity

- Stats contain tool names, call counts, and response sizes — not response content
- No PII in analytics data
- Namespace-scoped: one namespace cannot see another's stats

### 8.2 Access Control

- All stats tools require read access to the namespace
- Suggestion tool is read-only — it recommends but doesn't apply changes

---

## 9. Testing Requirements

### 9.1 Unit Tests

- Telemetry capture produces correct Redis commands
- Stats aggregation computes correct averages/counts from sorted set data
- Suggestion engine generates correct recommendations for each rule
- Token estimation calculation

### 9.2 Integration Tests

- Proxy call → telemetry captured → stats query returns the call
- Multiple calls → aggregation returns correct per-tool breakdown
- Suggestion engine with real stats → actionable recommendations

---

## 10. Future Considerations

### 10.1 Phase 2: Console Analytics Dashboard

- Visual charts for call volume, latency, response sizes over time
- Per-server and per-tool drill-down
- Token savings graph

### 10.2 Phase 2: Cost Estimation

- User configures their AI provider's per-token pricing
- Stats report includes estimated dollar savings

### 10.3 Phase 2: Auto-Optimization Mode

- User opts in to automatic rule application based on suggestions
- AI applies optimizations without asking (with audit trail)

---

## 11. Spec Completeness Checklist

- [x] Clear user value proposition stated
- [x] Success criteria defined and measurable
- [x] All functional requirements enumerated
- [x] All constraints documented
- [x] Error scenarios identified
- [x] Security requirements specified
- [x] Performance requirements quantified
- [x] Testing requirements defined
- [x] Observability requirements defined
- [ ] Logic checked
- [ ] Peer reviewed

---

## 12. Approval

**Status:** Draft

**Approvals:**
- [ ] CTO (Simon Carr)

---

## Changelog

**v0.1.0 (2026-03-26):**
- Full specification (upgraded from idea capture)
