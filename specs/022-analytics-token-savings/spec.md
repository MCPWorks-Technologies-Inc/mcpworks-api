# Feature Specification: MCP Proxy Analytics — Token Savings Tracking and REST API

**Feature Branch**: `022-analytics-token-savings`
**Created**: 2026-04-08
**Status**: Draft
**Input**: User description: "MCP Proxy Analytics — Token Savings Tracking and REST API. Extends existing analytics infrastructure (McpProxyCall, McpExecutionStat models, services/analytics.py) to: (1) track token savings for ALL executions not just MCP-proxy ones, by adding input_bytes column and removing the mcp_calls_count>0 guard; (2) expose analytics via REST API endpoints at /v1/analytics/* for dashboards; (3) add platform-wide aggregate token savings for admin/marketing (cross-namespace totals); (4) comprehensive unit tests. GitHub issue #53."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Namespace Owner Views Token Savings Dashboard (Priority: P1)

A namespace owner wants to see how many tokens MCPWorks is saving them. They visit a dashboard (or query the REST API) and see a clear report showing: how much data their functions processed, how much was returned to the AI, and the percentage saved. This is the proof that MCPWorks delivers on its "70-98% token savings" promise.

**Why this priority**: This is the core value proposition proof point. Without visible savings numbers, customers can't justify their subscription and the marketing claim is unverifiable.

**Independent Test**: Can be fully tested by calling `GET /v1/analytics/token-savings?namespace=X&period=30d` after running several function executions and verifying the response contains accurate savings calculations.

**Acceptance Scenarios**:

1. **Given** a namespace with 100 function executions in the last 24 hours, **When** the owner requests token savings for the "24h" period, **Then** they receive a report showing total executions, input bytes processed, result bytes returned, estimated tokens saved, and a savings percentage.
2. **Given** a namespace with zero executions, **When** the owner requests token savings, **Then** they receive a report with all values at zero and 0% savings (no errors).
3. **Given** a namespace with both direct function calls and MCP-proxy-backed executions, **When** the owner requests token savings, **Then** both types of execution are included in the totals.

---

### User Story 2 - All Executions Contribute to Analytics (Priority: P1)

Currently, only executions that make MCP proxy calls are tracked in analytics. A namespace owner running pure sandbox functions (no external MCP server calls) sees no analytics at all. After this feature, every function execution — whether it uses MCP proxy or not — records input size, output size, and token savings.

**Why this priority**: Without this, the majority of executions are invisible to analytics. The token savings dashboard would show incomplete data, undermining trust in the numbers.

**Independent Test**: Execute a pure sandbox function (no MCP proxy calls), then verify a record appears in execution stats with accurate input_bytes and result_bytes.

**Acceptance Scenarios**:

1. **Given** a function that takes 5KB of input arguments and returns a 200-byte result, **When** the function executes successfully, **Then** an analytics record is created showing input_bytes=~5000, result_bytes=~200, and tokens_saved_est reflecting the difference.
2. **Given** a code-mode execution that processes data in the sandbox, **When** the execution completes, **Then** analytics capture the code size as input and the output size as result.
3. **Given** an execution that fails, **When** the failure is recorded, **Then** the analytics record still captures the input size (result_bytes will be zero).

---

### User Story 3 - REST API Exposes Analytics for External Dashboards (Priority: P2)

A developer building a dashboard or integrating with external analytics tools (Datadog, Grafana, MCPCat) needs HTTP endpoints to query analytics data. The REST API provides token savings, per-server stats, per-function stats, and optimization suggestions — the same data already available via MCP tools but now over standard HTTP.

**Why this priority**: MCP tools are only accessible from AI assistants. Dashboards, monitoring systems, and external integrations need REST endpoints.

**Independent Test**: Authenticate with an API key and call each analytics endpoint, verifying correct JSON responses that match the existing MCP tool output format.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they call `GET /v1/analytics/token-savings?namespace=myns&period=7d`, **Then** they receive a JSON response with token savings data for their namespace.
2. **Given** an authenticated user, **When** they call `GET /v1/analytics/server-stats/google-workspace?namespace=myns`, **Then** they receive per-tool call counts, latency, error rates for that MCP server.
3. **Given** an unauthenticated request, **When** calling any analytics endpoint, **Then** a 401 error is returned.
4. **Given** an authenticated user requesting analytics for a namespace they don't own, **When** the request is processed, **Then** a 403/404 error is returned.

---

### User Story 4 - Platform Admin Views Aggregate Token Savings (Priority: P2)

A platform administrator (or marketing team) wants to see platform-wide token savings across all namespaces. This produces the headline number: "MCPWorks saved X million tokens this month across Y active namespaces." This data powers marketing materials, investor reports, and the website.

**Why this priority**: Platform-wide metrics drive marketing claims and business decisions. Without aggregate data, each namespace is an island.

**Independent Test**: As an admin user, call the admin analytics endpoint and verify it returns cross-namespace totals, active namespace count, and a top-namespaces breakdown.

**Acceptance Scenarios**:

1. **Given** 10 namespaces with execution data, **When** an admin requests platform token savings for "30d", **Then** they receive aggregate totals across all namespaces including total executions, total tokens saved, savings percentage, and active namespace count.
2. **Given** the aggregate report, **When** examining the response, **Then** it includes a "top namespaces" list ranked by tokens saved (up to 10 entries).
3. **Given** a non-admin user, **When** they attempt to access platform-wide analytics, **Then** access is denied.

---

### User Story 5 - Comprehensive Test Coverage (Priority: P3)

The analytics service has zero test coverage today. All analytics functions — recording, querying, aggregation, and suggestions — must have unit tests to prevent regressions as the analytics system evolves.

**Why this priority**: Test coverage is a quality gate, not a user-facing feature, but it protects the accuracy of all token savings calculations.

**Independent Test**: Run `pytest tests/unit/test_analytics.py` and verify all tests pass with meaningful assertions against known input data.

**Acceptance Scenarios**:

1. **Given** the analytics service module, **When** running unit tests, **Then** all recording functions, query functions, and the suggestion engine are covered with at least 80% line coverage and all edge cases documented in this spec.
2. **Given** edge cases (zero executions, division by zero, missing data), **When** tested, **Then** functions return sensible defaults without errors.

---

### Edge Cases

- What happens when a namespace has executions but zero result bytes (100% savings)? System reports 100% savings — this is valid (sandbox processed data, returned nothing to AI).
- How does the system handle very large input sizes (>100MB arguments)? Input size is recorded as-is; no cap needed since it's just an integer column.
- What happens when the analytics database write fails? Fire-and-forget pattern catches exceptions and logs a debug message — execution is unaffected.
- How does the savings calculation handle cases where result_bytes > input_bytes (negative "savings")? `max(0, ...)` ensures savings are never negative; savings_percent floors at 0%.
- What happens when the analytics tables are empty for a given period? All aggregate functions return zero values with 0% savings — no division-by-zero errors.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST record analytics for every function execution, regardless of whether MCP proxy calls were made.
- **FR-002**: System MUST capture input size (bytes) for each execution alongside the existing output size and MCP proxy bytes.
- **FR-003**: System MUST calculate token savings as `max(0, (max(mcp_bytes, input_bytes) - result_bytes)) / 4`, ensuring savings are never negative.
- **FR-004**: System MUST provide REST API endpoints for token savings, server stats, function stats, and optimization suggestions, authenticated and scoped to the requesting user's namespaces.
- **FR-005**: System MUST provide a platform-wide aggregate token savings endpoint restricted to admin users.
- **FR-006**: Analytics recording MUST be fire-and-forget (non-blocking) — failures must not affect function execution.
- **FR-007**: REST API responses MUST use the same data format as existing MCP analytics tools for consistency.
- **FR-008**: Token savings report MUST include: total executions, input bytes/tokens, MCP bytes/tokens, result bytes/tokens, tokens saved estimate, savings percentage, and top consumers.
- **FR-009**: Platform aggregate report MUST include: active namespace count, total executions, aggregate savings, and a ranked list of top namespaces by tokens saved.
- **FR-010**: All analytics endpoints MUST support period filtering (1h, 24h, 7d, 30d).
- **FR-011**: System MUST have unit test coverage for all analytics recording, querying, and suggestion functions.

### Key Entities

- **Execution Stat Record**: Represents analytics for a single function execution — captures input size, MCP proxy data volume, result size, and calculated token savings. Linked to a namespace and execution ID.
- **Proxy Call Record**: Represents a single MCP proxy tool call within an execution — captures server, tool, latency, response size, status, and injection detection results.
- **Token Savings Report**: An aggregated view over a time period showing totals, percentages, and top consumers for a namespace or platform-wide.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every function execution (both direct and MCP-proxy-backed) produces an analytics record within 1 second of completion.
- **SC-002**: Token savings reports accurately reflect all execution data for the requested period with less than 1% calculation error.
- **SC-003**: REST API analytics endpoints return responses within 500ms for namespaces with up to 100,000 execution records.
- **SC-004**: Platform aggregate endpoint returns results within 2 seconds across all namespaces.
- **SC-005**: Analytics recording adds less than 5ms of overhead to any function execution (fire-and-forget, non-blocking).
- **SC-006**: Unit test suite covers all analytics service functions with at least 80% line coverage and all edge cases documented in this spec.
- **SC-007**: A namespace owner can view their token savings within 30 seconds of their first function execution completing.

## Assumptions

- The existing McpProxyCall and McpExecutionStat database tables and indexes are sufficient for the query patterns described. No new tables are needed — only an input_bytes column addition to McpExecutionStat.
- Token estimation uses the standard approximation of 4 bytes per token.
- The REST API follows the existing authentication pattern (JWT/API key via require_active_status dependency).
- Admin endpoints follow the existing admin pattern (AdminUserId dependency).
- Analytics recording continues to use fire-and-forget asyncio.create_task() pattern for non-blocking persistence.
- Period options (1h, 24h, 7d, 30d) are sufficient for initial release; custom date ranges can be added later.
