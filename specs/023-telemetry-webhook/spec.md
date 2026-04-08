# Feature Specification: Namespace Telemetry Webhook

**Feature Branch**: `023-telemetry-webhook`
**Created**: 2026-04-08
**Status**: Draft
**Input**: User description: "Namespace telemetry webhook — fire-and-forget async webhook on every tool call for external analytics platforms (MCPCat, Datadog, OTel). Configurable per-namespace with URL + HMAC secret. Webhook payload contains execution metadata only (no input/output data). Optional Redis batching. Generic HTTP POST with SHA-256 HMAC signature. GitHub issue #46."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Namespace Owner Connects External Analytics (Priority: P1)

A namespace owner wants their function execution data to appear in their existing analytics platform (MCPCat, Datadog, PostHog, or any HTTP endpoint). They configure a webhook URL on their namespace, and from that point forward every tool call automatically sends execution metadata to that endpoint. No code changes, no polling — just set the URL and data flows.

**Why this priority**: This is the core feature. Without webhook delivery, there's nothing to configure or secure. Every other story depends on this.

**Independent Test**: Configure a webhook URL on a namespace, execute a function, and verify the external endpoint receives an HTTP POST with execution metadata within 5 seconds.

**Acceptance Scenarios**:

1. **Given** a namespace with a webhook URL configured, **When** a function executes successfully, **Then** the webhook endpoint receives a POST with event type, function name, execution time, success status, and timestamp.
2. **Given** a namespace with a webhook URL configured, **When** a function execution fails, **Then** the webhook fires with `success: false` and the error type (but never the error message content or input/output data).
3. **Given** a namespace with no webhook URL configured, **When** a function executes, **Then** no webhook is sent and there is zero additional overhead.
4. **Given** a namespace with a webhook URL that is unreachable, **When** a function executes, **Then** the function execution completes normally (webhook failure never blocks or delays execution).

---

### User Story 2 - Webhook Payload Signature Verification (Priority: P1)

A namespace owner wants assurance that webhook payloads are authentic and haven't been tampered with. They configure an HMAC secret alongside their webhook URL. Every outbound payload is signed with SHA-256 HMAC, and the receiving endpoint can verify the signature before trusting the data.

**Why this priority**: Without signature verification, webhook endpoints are vulnerable to spoofing. This is table-stakes security for any webhook system (same pattern as GitHub, Stripe, Shopify webhooks).

**Independent Test**: Configure a webhook with a secret, trigger an execution, capture the payload and signature header, and verify the HMAC matches using the secret.

**Acceptance Scenarios**:

1. **Given** a namespace with both webhook URL and secret configured, **When** a webhook fires, **Then** the HTTP request includes a signature header computed as SHA-256 HMAC of the payload body using the secret.
2. **Given** the signature header, **When** the receiver computes the same HMAC using their copy of the secret, **Then** the signatures match exactly.
3. **Given** a namespace with a webhook URL but no secret configured, **When** a webhook fires, **Then** no signature header is included (signature is optional).

---

### User Story 3 - Configure Webhook via MCP Tools and REST API (Priority: P2)

A namespace owner (or their AI assistant) needs to set up, update, and remove webhook configuration. This is available through both the MCP create handler tools and the REST API, following the same patterns as other namespace configuration.

**Why this priority**: Configuration is essential but the delivery mechanism (US1) must work first.

**Independent Test**: Use the MCP tool or REST endpoint to set a webhook URL + secret, verify the configuration persists, then remove it and verify webhooks stop.

**Acceptance Scenarios**:

1. **Given** a namespace owner, **When** they set a webhook URL via the configuration tool, **Then** the URL is stored and subsequent executions trigger webhooks.
2. **Given** a configured webhook, **When** the owner updates the URL, **Then** future webhooks go to the new URL.
3. **Given** a configured webhook, **When** the owner removes the URL (sets to null/empty), **Then** webhooks stop immediately.
4. **Given** a webhook secret, **When** stored, **Then** the secret is encrypted at rest (never stored in plaintext).

---

### User Story 4 - Event Batching for High-Volume Namespaces (Priority: P3)

A high-volume namespace generating thousands of executions per minute wants to avoid overwhelming their webhook endpoint with individual HTTP calls. They enable batching, which buffers events and delivers them in batches at a configurable interval (e.g., every 5 or 10 seconds).

**Why this priority**: Nice-to-have optimization. Most namespaces won't need this initially, but high-volume enterprise customers will.

**Independent Test**: Enable batching with a 5-second interval, trigger 50 rapid executions, and verify the endpoint receives batched payloads (arrays of events) rather than 50 individual calls.

**Acceptance Scenarios**:

1. **Given** batching enabled with a 5-second flush interval, **When** 20 events occur within 5 seconds, **Then** the endpoint receives a single POST containing an array of 20 events.
2. **Given** batching enabled, **When** fewer events than the batch size occur before the flush interval, **Then** the partial batch is delivered at the interval boundary (no events are lost).
3. **Given** batching disabled (default), **When** events occur, **Then** each event is delivered individually as in US1.

---

### User Story 5 - Unit Tests for Webhook System (Priority: P3)

The webhook delivery, signing, batching, and configuration must have comprehensive unit tests to ensure reliability and prevent regressions.

**Why this priority**: Quality gate that protects the integrity of the webhook system.

**Independent Test**: Run the webhook test suite and verify all functions are covered with meaningful assertions.

**Acceptance Scenarios**:

1. **Given** the webhook service module, **When** running unit tests, **Then** delivery, signing, error handling, and batching logic are covered with at least 80% line coverage.
2. **Given** edge cases (unreachable URL, malformed URL, empty secret, oversized payload), **When** tested, **Then** functions handle them gracefully without exceptions.

---

### Edge Cases

- What happens when the webhook URL returns a non-2xx status? The event is logged and dropped — no retries in v1 (retries deferred to future enhancement).
- What happens when the webhook URL is malformed (not a valid HTTP/HTTPS URL)? Rejected at configuration time with a validation error.
- What happens when the payload exceeds a reasonable size? Individual events are capped at execution metadata only (~500 bytes); batches are capped at 1000 events per flush.
- What happens when Redis is unavailable and batching is enabled? Falls back to individual delivery (fire-and-forget, same as non-batched mode).
- What happens during a namespace ownership transfer? Webhook config stays with the namespace, not the user.
- Can the same webhook URL be used on multiple namespaces? Yes — each namespace sends independently.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST send an HTTP POST to the configured webhook URL on every successful or failed function execution within the namespace.
- **FR-002**: Webhook delivery MUST be fire-and-forget — it must never block, delay, or cause failure of the function execution.
- **FR-003**: Webhook payload MUST contain only execution metadata: event type, namespace, function name, execution ID, execution time, success/failure status, backend type, function version, and timestamp. It MUST NOT contain function input arguments, output data, error messages, or any user-provided content.
- **FR-004**: System MUST support HMAC-SHA256 signature of the payload body, included as a request header, when a webhook secret is configured.
- **FR-005**: Webhook URL MUST be validated as a well-formed HTTPS URL at configuration time (HTTP allowed only for localhost/development).
- **FR-006**: Webhook secret MUST be encrypted at rest using the existing encryption infrastructure.
- **FR-007**: System MUST provide configuration tools (both MCP and REST) to set, update, and remove webhook URL and secret per namespace.
- **FR-008**: System MUST support optional event batching with a configurable flush interval (default: disabled).
- **FR-009**: When batching is enabled and the buffering system is unavailable, the system MUST fall back to individual event delivery.
- **FR-010**: System MUST log webhook delivery attempts and failures (success/error, latency, HTTP status) for observability.
- **FR-011**: System MUST have unit test coverage for webhook delivery, signing, error handling, and batching logic.

### Key Entities

- **Telemetry Webhook Config**: Per-namespace configuration containing the destination URL, optional HMAC secret (encrypted), and optional batching settings (enabled flag, flush interval). Stored as part of namespace data.
- **Telemetry Event**: A lightweight execution metadata record sent to the webhook endpoint. Contains event type, namespace name, function identifier, execution timing, success status, and timestamp. Never contains user data.
- **Telemetry Batch**: An ordered array of telemetry events delivered as a single HTTP POST when batching is enabled.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Webhook delivery adds less than 5ms of overhead to function execution (fire-and-forget, non-blocking).
- **SC-002**: 99% of webhook deliveries arrive at the destination within 5 seconds of function execution completion (excluding batched events which arrive at the next flush interval).
- **SC-003**: Namespace owners can configure a webhook and see events flowing to their endpoint within 2 minutes of setup.
- **SC-004**: Webhook payload size is under 1KB per individual event, keeping bandwidth costs negligible.
- **SC-005**: System handles webhook endpoint failures gracefully — zero impact on function execution, failures logged for debugging.
- **SC-006**: Unit test suite covers all webhook functions with at least 80% line coverage.
- **SC-007**: HMAC signature verification succeeds 100% of the time when the correct secret is used (no encoding or serialization mismatches).

## Assumptions

- HTTPS is required for webhook URLs in production; HTTP is allowed only for localhost (development/testing convenience).
- No retry mechanism in v1 — failed deliveries are logged and dropped. Retry with exponential backoff can be added in a future enhancement.
- Batching uses the existing Redis infrastructure. If Redis is not available, batching is silently disabled.
- The webhook secret uses the same encryption system already in place for MCP server credentials (envelope encryption).
- Individual event payload is approximately 300-500 bytes of JSON; batch payloads are capped at 1000 events (~500KB max).
- The signature header name follows the `X-MCPWorks-Signature` convention (similar to `X-Hub-Signature-256` used by GitHub).
- Webhook configuration is per-namespace, not per-function or per-service. A namespace owner who wants different endpoints for different functions would use a routing proxy on their side.
