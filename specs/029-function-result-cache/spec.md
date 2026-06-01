# Feature Specification: Function Result Caching (Redis)

**Feature Branch**: `029-function-result-cache`  
**Created**: 2026-04-15  
**Status**: Draft  
**Input**: User description: "#44 — Function result caching (Redis). Cache function results by function_id + hash(input) in Redis with configurable per-function TTL."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cache deterministic function results (Priority: P1)

A namespace owner has a deterministic function (e.g., currency conversion, template rendering) that gets called repeatedly with the same inputs. They enable caching on the function with a TTL of 5 minutes. Subsequent identical calls within the TTL window return instantly from Redis without spinning up a sandbox, saving compute and reducing latency from seconds to milliseconds.

**Why this priority**: This is the core value — latency reduction and compute savings for repeat calls. Without this, the feature has no purpose.

**Independent Test**: Call a cached function twice with identical inputs. First call executes in sandbox (~2s). Second call returns from cache (~10ms). Both return identical output.

**Acceptance Scenarios**:

1. **Given** a function with caching enabled (TTL 300s), **When** it is called twice with the same input within 300s, **Then** the second call returns the cached result without sandbox execution, with latency under 50ms.
2. **Given** a function with caching enabled, **When** it is called and execution fails (error result), **Then** the error is NOT cached — the next call executes fresh.
3. **Given** a function with caching enabled, **When** it is called with different inputs, **Then** each unique input set gets its own cache entry.
4. **Given** a function with caching disabled (default), **When** it is called, **Then** every call goes to sandbox — no cache interaction.

---

### User Story 2 - Caller bypasses cache (Priority: P2)

A caller needs a fresh result for a cached function (e.g., testing a code change, debugging stale data). They pass a `cache: false` flag in the function call to force fresh execution and update the cache with the new result.

**Why this priority**: Essential escape hatch — without bypass, stale cache is unfixable until TTL expires.

**Independent Test**: Call a cached function with `cache: false`. Verify sandbox execution occurs even when a cached result exists, and the cache is updated with the fresh result.

**Acceptance Scenarios**:

1. **Given** a cached result exists for a function+input pair, **When** the caller passes `cache: false`, **Then** the function executes in sandbox and the cache is updated with the new result.

---

### User Story 3 - Cache hit/miss observability (Priority: P3)

An operator wants to understand cache effectiveness across functions. Cache hits and misses are tracked as Prometheus metrics, and cache status is included in execution metadata so it's visible in execution history.

**Why this priority**: Without observability, operators can't measure whether caching is actually helping or needs tuning.

**Independent Test**: After a cache hit, verify the Prometheus cache_hits counter incremented and the execution record shows `cache_hit: true`.

**Acceptance Scenarios**:

1. **Given** a cache hit occurs, **When** metrics are scraped, **Then** the `function_cache_hits_total` counter has incremented with namespace and function labels.
2. **Given** a cache miss followed by execution, **When** the execution record is examined, **Then** it includes cache status metadata (hit/miss).

---

### Edge Cases

- What happens when Redis is down? Function executes normally without caching — Redis failure must never block execution.
- What happens when the cached result is corrupted (invalid JSON)? Treat as cache miss, execute fresh, overwrite the corrupt entry.
- What happens when a function is updated to a new version? Cache keys include the version number, so the old cache is naturally orphaned and expires via TTL.
- What happens when the cache value exceeds Redis memory? Redis eviction policy handles this — the application does not manage eviction.
- What happens when two identical calls arrive simultaneously (cold cache)? Both execute — no thundering herd protection for v1 (documented as non-goal).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support per-function cache configuration via a cache policy setting (enabled flag + TTL in seconds).
- **FR-002**: Cache keys MUST be derived from function ID, active version number, and a deterministic hash of the input parameters.
- **FR-003**: System MUST check Redis for a cached result before dispatching to the sandbox backend.
- **FR-004**: System MUST store successful execution results in Redis with the configured TTL after sandbox execution.
- **FR-005**: System MUST NOT cache error results (only successful executions are cached).
- **FR-006**: Callers MUST be able to bypass the cache by passing a flag, forcing fresh execution and updating the cache.
- **FR-007**: Caching MUST be disabled by default — functions only cache when explicitly configured.
- **FR-008**: System MUST degrade gracefully when Redis is unavailable — function execution proceeds without caching.
- **FR-009**: System MUST track cache hits and misses as Prometheus counters with namespace and function name labels.
- **FR-010**: Cache status (hit/miss) MUST be included in execution metadata for observability.
- **FR-011**: Namespace owners MUST be able to configure cache policy via the MCP create endpoint.

### Key Entities

- **Cache Policy**: Per-function configuration containing `enabled` (boolean) and `ttl_seconds` (integer, default 300). Stored on the function model.
- **Cache Entry**: A Redis key-value pair where the key encodes function identity + input hash, and the value is the serialized execution result. Expires automatically via Redis TTL.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Cached function calls return in under 50ms (vs 1-5 seconds for sandbox execution).
- **SC-002**: Cache hit rate for a function called 10 times with identical inputs within TTL window is 90% (9 hits, 1 miss).
- **SC-003**: Redis failure does not cause any function call to fail — degradation is invisible to the caller.
- **SC-004**: Cache entries expire automatically at the configured TTL — no manual cleanup required.
- **SC-005**: Operators can measure cache effectiveness via Prometheus metrics within 24 hours of enabling caching on a function.

## Assumptions

- Redis is already deployed and connected in all environments (production, development).
- The existing `config` JSONB field on the Function model can be extended to include cache policy, avoiding a schema migration.
- Input canonicalization uses sorted JSON serialization for deterministic hashing.
- Cache values are stored as JSON strings in Redis — the serialized ExecutionResult output.
- No thundering herd protection in v1 — simultaneous cold-cache calls all execute. This is acceptable given the expected call volume.
