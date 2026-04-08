# Research: Namespace Telemetry Webhook

**Date**: 2026-04-08

## R1: Webhook Delivery Pattern

**Decision**: `asyncio.create_task()` with `httpx.AsyncClient` for individual events; no connection pooling per namespace.

**Rationale**: Same fire-and-forget pattern used by `services/analytics.py` and `services/discord_alerts.py`. httpx is already a dependency. A single shared `httpx.AsyncClient` with connection pooling would be better at scale but adds lifecycle management complexity. For v1, create a fresh client per delivery — httpx handles connection cleanup automatically.

**Alternatives considered**:
- aiohttp: Not in dependency tree; httpx already available.
- Connection pool per namespace: Better performance but requires pool lifecycle management. Deferred.
- Background worker queue (Celery/RQ): Too heavy for fire-and-forget telemetry.

## R2: HMAC Signing Implementation

**Decision**: SHA-256 HMAC of the raw JSON payload bytes, delivered as `X-MCPWorks-Signature: sha256=<hex_digest>`.

**Rationale**: Follows the GitHub webhook signature convention (`X-Hub-Signature-256`). SHA-256 HMAC is the industry standard — used by GitHub, Stripe, Shopify, Slack. The signature covers the entire POST body (raw bytes, not the parsed JSON) to prevent serialization-order attacks.

**Alternatives considered**:
- SHA-1 HMAC: Deprecated, collision attacks possible.
- Ed25519 signatures: Stronger but requires key pair management. Overkill for webhook verification.
- JWT-signed payloads: More complex, no benefit over HMAC for this use case.

## R3: Secret Encryption at Rest

**Decision**: Use existing `encrypt_value()`/`decrypt_value()` from `core/encryption.py` (AES-256-GCM envelope encryption with KEK/DEK).

**Rationale**: Same pattern used for MCP server credentials (`NamespaceMcpServer.headers_encrypted`). Two columns: `telemetry_webhook_secret_encrypted` (ciphertext) and `telemetry_webhook_secret_dek` (encrypted DEK). The webhook URL itself is NOT encrypted — it's not a secret (the URL pattern is visible in HTTP logs regardless).

**Alternatives considered**:
- Store plaintext secret with application-level access control: Violates security-by-default principle.
- Use a separate secrets manager (Infisical): Not yet deployed; would add infrastructure dependency.

## R4: Batching Strategy

**Decision**: Redis LIST per namespace as event buffer, flushed by a periodic task every N seconds.

**Rationale**: Redis is already deployed and used for rate limiting. LPUSH is O(1), LRANGE+LTRIM for flush is O(N). The periodic task uses the existing APScheduler infrastructure. Batching is opt-in — disabled by default.

**Alternatives considered**:
- In-memory buffer: Lost on process restart; no cross-worker sharing.
- PostgreSQL as buffer: Too heavy for write-intensive buffering.
- Kafka/NATS: Not in infrastructure; massive overkill for this use case.

## R5: Webhook URL Validation

**Decision**: Validate at configuration time — must be well-formed HTTPS URL. Allow HTTP only for `localhost` and `127.0.0.1` (development). Reject private IPs (10.x, 172.16-31.x, 192.168.x) except localhost.

**Rationale**: Prevents SSRF attacks where a malicious user could configure a webhook pointing to internal infrastructure. Localhost exception enables development/testing.

**Alternatives considered**:
- Allow any URL: SSRF risk.
- Allow only HTTPS, no exceptions: Blocks local development.
- DNS resolution check at config time: Race condition (DNS can change after validation).
