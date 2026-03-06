# Infrastructure Scaling Plan

From one box to 500 customers. Trigger-based — scale when metrics say so, not before.

**Companion to:** [PLAN.md](PLAN.md) (single-box observability stack)

---

## What's Already Scale-Ready

These were built correctly from the start and won't need rework:

| Component | Why It Scales | Code Reference |
|-----------|---------------|----------------|
| MCP transport | `stateless=True` — each POST creates a fresh session, no affinity needed | `mcp/transport.py:84` |
| Authentication | Stateless JWT (ES256), no server-side sessions to synchronize | `config.py:48` |
| Billing/quotas | Redis-backed monthly counters, shared across any number of API instances | `middleware/billing.py` |
| Rate limiting | Redis-backed, works across instances | `middleware/rate_limit.py` |
| Structured logging | structlog JSON with correlation IDs, namespace labels — ready for centralized collection | `middleware/` |
| Prometheus metrics | `/metrics` endpoint with namespace/service labels, low-cardinality design | `middleware/metrics.py` |
| Provider abstraction | Backend interface decouples execution from infrastructure | `backends/base.py` |

---

## What Breaks at Scale

### 1. Database Connection Pooling

**Current:** `pool_size=5`, `max_overflow=10` → 15 connections max per API instance (`config.py:32-33`).

**Problem:** Postgres default `max_connections=100`. Two API instances = 30 connections. Four instances = 60. Add Alembic migrations, admin queries, monitoring — you're at the wall.

**When it breaks:** 3+ API instances, or sustained load on 2 instances with concurrent sandbox executions.

### 2. Redis Single Point of Failure

**Current:** Single Redis container (`docker-compose.prod.yml:98`), used for billing quotas and rate limiting.

**Problem:** If Redis dies, the billing middleware can't check quotas. Current behavior: requests fail with 500. No quota enforcement = potential over-usage or total outage depending on error handling path.

**When it breaks:** Any Redis crash. Risk grows with uptime commitments.

### 3. Caddy Single Point of Failure

**Current:** Single Caddy container handles all TLS termination and reverse proxying (`docker-compose.prod.yml:4`).

**Problem:** Caddy restart = full outage. No health-check-based failover. Wildcard cert renewal failure = extended outage.

**When it breaks:** Any Caddy crash or cert renewal issue. Unacceptable once SLA commitments exist.

### 4. Sandbox Concurrency

**Current:** nsjail sandboxes run on the API container itself (privileged, `SYS_ADMIN` caps). Each execution allocates up to 512MB RAM (Pro tier) with 64 PIDs (`backends/sandbox.py:45-70`).

**Problem:** On a 4GB droplet with Postgres, Redis, Caddy, and the API all co-resident, realistic concurrent sandbox capacity is 10-20 executions. At 500 customers, peak concurrent demand could be 50-250.

**When it breaks:** 100+ customers with active sandbox usage. Queue depth grows, p99 latency spikes.

### 5. Fire-and-Forget Security Events

**Current:** Security events and emails dispatched via `asyncio.create_task()` — if the process crashes mid-flight, those events are lost.

**References:** `middleware/rate_limit.py:65`, `middleware/billing.py:68`, `mcp/router.py:62`, `backends/sandbox.py:416`, `services/auth.py:240`

**Problem:** Acceptable at small scale (low crash frequency, low event volume). At scale, crashes during deploys or OOM kills lose audit data that compliance requires.

**When it breaks:** When audit completeness matters (SOC 2, enterprise customers).

### 6. Prometheus Cardinality Ceiling

**Current:** Budget from PLAN.md — 37,000 series at 500 namespaces on a 4GB mgmt droplet. Ceiling is ~50,000 before OOM.

**Problem:** Growth beyond 500 namespaces, or adding per-service labels, pushes past the ceiling. Prometheus on the mgmt droplet OOM-kills.

**When it breaks:** 500+ namespaces, or cardinality label mistakes.

---

## Scaling Phases

### Phase 1: Vertical (0-100 customers)

**What you have today.** Single prod droplet, single mgmt droplet.

| Component | Spec | Monthly Cost |
|-----------|------|-------------|
| Prod droplet (API + Postgres + Redis + Caddy + Sandbox) | s-2vcpu-4gb | $24 |
| Mgmt droplet (Grafana + Prometheus + Loki + Uptime Kuma) | s-2vcpu-4gb | $24 |
| **Total** | | **$48** |

**Actions at this phase:**
- Deploy mgmt stack per PLAN.md
- Set up alerts for the Phase 2 triggers below
- Monitor `prometheus_tsdb_head_series`, API p99, Postgres connection count

**Trigger to Phase 2:**
- API p99 latency > 500ms sustained 15min
- Postgres connection warnings in logs (`remaining connection slots are reserved`)
- Sandbox queue depth > 5 (executions waiting for a slot)
- Prod droplet CPU > 70% sustained 10min

---

### Phase 2: Extract Stateful Services (100-250 customers)

Move Postgres and Redis off the prod droplet. This frees CPU and RAM for the API and sandbox, and removes the blast radius of a sandbox OOM killing the database.

| Component | Spec | Monthly Cost |
|-----------|------|-------------|
| Prod droplet (API + Caddy + Sandbox) | s-4vcpu-8gb | $48 |
| DO Managed Postgres | db-s-1vcpu-2gb (1 primary, daily backups) | $30 |
| DO Managed Redis/Valkey | db-s-1vcpu-1gb (HA standby) | $20 |
| Mgmt droplet | s-2vcpu-4gb | $24 |
| **Total** | | **$122** |

**Actions:**
1. **Managed Postgres** — Migrate with `pg_dump`/`pg_restore`. Update `DATABASE_URL`. Managed service handles backups, failover, and connection limits (25 connections on the $15 plan; upgrade to $30 plan for 50 connections if needed).
2. **PgBouncer** — Add PgBouncer sidecar on the prod droplet. Set `pool_mode=transaction`, `default_pool_size=20`, `max_client_conn=100`. This multiplexes application connections over fewer Postgres connections, buying headroom for Phase 3 horizontal scaling.
3. **Managed Redis/Valkey** — DO Managed Database for Redis ($15/mo for single node, $20/mo with HA standby). Update `REDIS_URL`.
4. **Redis fail-closed** — Update billing middleware: if Redis is unreachable, reject execution requests (fail closed) rather than allowing unlimited executions. A 30-second circuit breaker retries before hard-failing.
5. **Upsize prod droplet** — s-4vcpu-8gb gives the sandbox room. Concurrent capacity goes from ~15 to ~40.

**Trigger to Phase 3:**
- Sandbox queue depth > 10 sustained 5min
- Prod droplet CPU > 80% sustained 10min
- Concurrent sandbox executions consistently near capacity

---

### Phase 3: Horizontal Compute (250-400 customers)

Add a second API box behind a load balancer. Split sandbox execution to a dedicated worker.

| Component | Spec | Monthly Cost |
|-----------|------|-------------|
| API droplet × 2 | s-4vcpu-8gb × 2 | $96 |
| Sandbox worker droplet | s-4vcpu-8gb (dedicated to nsjail) | $48 |
| DO Load Balancer | Small (10 req/s baseline) | $12 |
| DO Managed Postgres | db-s-2vcpu-4gb (connection headroom) | $60 |
| DO Managed Redis/Valkey | db-s-1vcpu-2gb (HA standby) | $30 |
| Mgmt droplet | s-2vcpu-4gb | $24 |
| **Total** | | **$270** |

**Actions:**
1. **DO Load Balancer** — $12/mo. Health check on `/v1/health`. Round-robin distribution. No sticky sessions needed (stateless JWT + stateless MCP). Wildcard TLS for `*.create.mcpworks.io` and `*.run.mcpworks.io` terminated at the LB.
2. **Second API droplet** — Identical container deployment. PgBouncer on each box. Since MCP transport is stateless and auth is JWT-based, no session synchronization needed.
3. **Sandbox worker** — Dedicated droplet running only sandbox executions. API dispatches execution requests to the worker via a Redis task queue (Celery with Redis broker, or a lightweight asyncio consumer). This isolates sandbox resource usage from API request handling.
4. **Task queue for sandbox** — Replace direct `asyncio.create_subprocess_exec()` with a Celery task (or Redis Streams consumer). API enqueues `{code, env, tier, timeout}`, worker dequeues and executes in nsjail, returns result. Timeout and retry handled at the queue level.
5. **Security events to queue** — Replace `asyncio.create_task()` fire-and-forget with the same task queue. Security events and emails become durable — they survive process crashes.

**Architecture:**

```
          ┌──────────────────┐
          │  DO Load Balancer │  ← Wildcard TLS, round-robin
          └────────┬─────────┘
          ┌────────┴─────────┐
          ▼                  ▼
    ┌──────────┐      ┌──────────┐
    │ API + PB │      │ API + PB │   ← Stateless, PgBouncer sidecar
    └─────┬────┘      └────┬─────┘
          │                │
          ▼                ▼
    ┌──────────┐    ┌──────────┐
    │ Managed  │    │ Managed  │
    │ Postgres │    │  Redis   │   ← Shared state
    └──────────┘    └──┬───────┘
                       │
                       ▼
               ┌──────────────┐
               │   Sandbox    │
               │   Worker     │   ← Dedicated nsjail execution
               └──────────────┘
```

**Trigger to Phase 4:**
- Either API box at 80% CPU sustained 10min
- Sandbox worker at 80% CPU sustained 10min
- API p99 latency > 500ms sustained 15min despite horizontal scaling

---

### Phase 4: Full Horizontal (400-500 customers)

Scale out all components. Add read replicas for query-heavy dashboards/analytics.

| Component | Spec | Monthly Cost |
|-----------|------|-------------|
| API droplet × 3 | s-4vcpu-8gb × 3 | $144 |
| Sandbox worker × 2 | s-4vcpu-8gb × 2 | $96 |
| DO Load Balancer | Small | $12 |
| DO Managed Postgres | db-s-4vcpu-8gb + 1 read replica | $120 |
| DO Managed Redis/Valkey | db-s-2vcpu-4gb (HA) | $45 |
| Mgmt droplet | s-4vcpu-8gb (VictoriaMetrics) | $48 |
| DO Spaces (log archive) | 250 GB | $5 |
| **Total** | | **$470** |

**Actions:**
1. **Third API box** — Same deployment. PgBouncer manages connection fan-out.
2. **Second sandbox worker** — Redis queue distributes work across both workers. Celery concurrency settings per worker.
3. **Postgres read replica** — Route read-heavy queries (admin dashboards, analytics, audit log queries) to the replica. Write path unchanged.
4. **VictoriaMetrics** — Replace Prometheus on the mgmt droplet. Drop-in compatible, handles 500K+ active series in the same RAM. No query/config changes needed.
5. **Loki log archival** — Ship logs older than 7 days to DO Spaces ($5/250GB/mo) for compliance retention. Active query window stays 7 days.
6. **Table partitioning** — Partition `executions`, `audit_logs`, and `security_events` tables by month. Keeps query performance stable as data grows. Old partitions are cheap to archive or drop.

---

## Component Deep Dives

### Database Scaling Path

| Phase | Setup | Max Connections | Monthly Cost |
|-------|-------|----------------|-------------|
| 1 | Local Postgres in Docker | 100 (default) | $0 (on prod droplet) |
| 2 | DO Managed db-s-1vcpu-2gb + PgBouncer | 25 Postgres / 100 app-side | $30 |
| 3 | DO Managed db-s-2vcpu-4gb + PgBouncer × 2 | 50 Postgres / 200 app-side | $60 |
| 4 | DO Managed db-s-4vcpu-8gb + read replica | 100 Postgres / 300 app-side | $120 |

**PgBouncer config (add to prod docker-compose):**
```ini
[pgbouncer]
pool_mode = transaction
default_pool_size = 20
max_client_conn = 100
reserve_pool_size = 5
server_idle_timeout = 300
```

**SQLAlchemy change** — Point `DATABASE_URL` at PgBouncer (port 6432) instead of Postgres directly. Reduce `pool_size` to 3 since PgBouncer handles pooling:
```python
database_pool_size: int = Field(default=3, ge=1, le=20)
database_max_overflow: int = Field(default=5, ge=0, le=30)
```

**Partitioning (Phase 4):**
```sql
-- Monthly partitions for high-volume tables
ALTER TABLE executions RENAME TO executions_old;
CREATE TABLE executions (LIKE executions_old INCLUDING ALL) PARTITION BY RANGE (created_at);
CREATE TABLE executions_2026_03 PARTITION OF executions
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
-- Automate with pg_partman extension
```

### Redis Scaling Path

| Phase | Setup | Monthly Cost |
|-------|-------|-------------|
| 1 | Local Redis in Docker | $0 (on prod droplet) |
| 2 | DO Managed db-s-1vcpu-1gb (HA standby) | $20 |
| 3 | Same + task queue broker duties | $30 |
| 4 | DO Managed db-s-2vcpu-4gb (HA) | $45 |

**Fail-closed pattern (implement at Phase 2):**
```python
async def check_quota(account_id: str, tier: str) -> bool:
    try:
        usage = await redis.get(f"usage:{account_id}:{month}")
        return int(usage or 0) < TIER_LIMITS[tier]
    except RedisError:
        # Fail closed: deny execution if Redis is down
        logger.error("redis_unavailable", action="quota_check_denied")
        return False
```

**What Redis stores (current):**
- `usage:{account_id}:{YYYY-MM}` — monthly execution count (TTL: 35 days)
- `rate:{ip}:{minute}` — rate limit counters (TTL: 60s)
- `rate:auth:{ip}` — auth failure counters (TTL: 60s)

**What Redis adds (Phase 3):**
- Celery broker queues for sandbox task dispatch
- Task results (short TTL, 5 min)

### Sandbox Scaling Path

| Phase | Setup | Concurrent Capacity | Monthly Cost |
|-------|-------|---------------------|-------------|
| 1 | nsjail on API droplet (4GB) | ~15 | $0 (on prod droplet) |
| 2 | nsjail on API droplet (8GB) | ~40 | $0 (on prod droplet) |
| 3 | Dedicated worker droplet (8GB) | ~80 | $48 |
| 4 | 2 worker droplets (8GB each) | ~160 | $96 |

**Capacity math** (Pro tier worst case: 512MB per sandbox):
- 8GB droplet, ~6GB usable after OS: 6,000 / 512 ≈ 12 concurrent max at peak memory
- But most executions are Free/Builder tier (128-256MB), and most finish in <10s
- Realistic sustained concurrency: ~40 per 8GB box (weighted average ~200MB per sandbox)

**Task queue architecture (Phase 3):**
```
API process                    Sandbox worker
    │                              │
    ├─ enqueue(code, env, tier) ──►│
    │      via Redis               │
    │                              ├─ nsjail execute
    │                              │
    │◄── result (stdout/stderr) ───┤
    │      via Redis               │
```

Use Celery with Redis broker. Worker runs with `--concurrency=8` (or tuned per tier mix). Task timeout matches tier config (10s-300s). Dead letter queue for failed executions.

### Load Balancing

**DO Load Balancer** — $12/mo, no configuration complexity.

- **Algorithm:** Round-robin (all API boxes are identical)
- **Health check:** HTTP GET `/v1/health` every 10s, 3 failures = remove from pool
- **TLS:** Wildcard cert for `*.create.mcpworks.io` and `*.run.mcpworks.io` via Let's Encrypt. Caddy on each API box handles app-level TLS; LB does TCP passthrough, OR LB terminates TLS and forwards HTTP internally.
- **Sticky sessions:** Not needed. JWT auth is stateless, MCP transport is stateless.
- **Websockets/SSE:** LB supports forwarding. No special config.

**Migration from Caddy:** In Phase 3, Caddy moves from "edge reverse proxy" to "local app server" on each API box. The DO LB becomes the edge. Caddy still handles per-request routing (create vs run endpoints), but TLS termination shifts to the LB.

### Observability Scaling Path

| Phase | Metrics Backend | Series Limit | Monthly Cost |
|-------|----------------|--------------|-------------|
| 1-2 | Prometheus on mgmt (4GB) | ~50,000 | $0 (on mgmt droplet) |
| 3 | Prometheus on mgmt (4GB) | ~50,000 | $0 (on mgmt droplet) |
| 4 | VictoriaMetrics on mgmt (8GB) | ~500,000 | $48 (mgmt upgrade) |

**VictoriaMetrics migration (Phase 4):**
- Drop-in Prometheus replacement. Same PromQL, same scrape configs.
- 7-10x less RAM per series than Prometheus.
- Single binary, no operator/sharding complexity.
- Existing Grafana dashboards work unchanged — just swap the datasource URL.

**Loki scaling:**
- Phases 1-3: Single-instance Loki on mgmt droplet. 7-day retention, query range limited to 24h.
- Phase 4: Add DO Spaces as Loki storage backend for archival. Active query stays 7 days on local disk. Archived logs queryable but slower.

**Grafana:** Never needs scaling. Single instance handles any number of dashboards and users. Memory stays under 512MB.

---

## Cost Model

### Revenue vs. Infrastructure

Using FINANCIAL-PLAN.md moderate scenario (Value Ladder pricing: Builder $49, Pro $149, Enterprise $499+). Blended ARPU ~$119/mo per paying customer.

| Phase | Paying Customers | Revenue/mo (Moderate) | Infra Cost/mo | Infra Margin |
|-------|-----------------|----------------------|---------------|-------------|
| 1 | 0-25 | $0-$2,925 | $48 | 98.4% at 25 |
| 2 | 25-133 | $2,925-$15,817 | $122 | 95.8%-99.2% |
| 3 | 133-200 | $15,817-$22,000 | $270 | 98.3%-98.8% |
| 4 | 200-265 | $22,000-$34,235 | $470 | 97.9%-98.6% |

**Margin never drops below 95%.** Infrastructure cost is negligible relative to revenue at every phase. See `mcpworks-internals/incoming/infrastructure-cost-deep-dive.md` for the full CFO-oriented cost analysis.

### Detailed Cost Breakdown

**Phase 1 ($48/mo):**
| Item | Cost |
|------|------|
| s-2vcpu-4gb (prod) | $24 |
| s-2vcpu-4gb (mgmt) | $24 |

**Phase 2 ($122/mo):**
| Item | Cost |
|------|------|
| s-4vcpu-8gb (prod) | $48 |
| DO Managed Postgres (db-s-1vcpu-2gb) | $30 |
| DO Managed Redis (db-s-1vcpu-1gb, HA) | $20 |
| s-2vcpu-4gb (mgmt) | $24 |

**Phase 3 ($270/mo):**
| Item | Cost |
|------|------|
| s-4vcpu-8gb × 2 (API) | $96 |
| s-4vcpu-8gb (sandbox worker) | $48 |
| DO Load Balancer | $12 |
| DO Managed Postgres (db-s-2vcpu-4gb) | $60 |
| DO Managed Redis (db-s-1vcpu-2gb, HA) | $30 |
| s-2vcpu-4gb (mgmt) | $24 |

**Phase 4 ($470/mo):**
| Item | Cost |
|------|------|
| s-4vcpu-8gb × 3 (API) | $144 |
| s-4vcpu-8gb × 2 (sandbox workers) | $96 |
| DO Load Balancer | $12 |
| DO Managed Postgres (db-s-4vcpu-8gb + replica) | $120 |
| DO Managed Redis (db-s-2vcpu-4gb, HA) | $45 |
| s-4vcpu-8gb (mgmt) | $48 |
| DO Spaces (250 GB) | $5 |

---

## Decision Points

Concrete metrics that trigger each transition. Set these as Grafana alerts.

### Phase 1 → Phase 2

| Metric | Threshold | Alert Severity |
|--------|-----------|---------------|
| `histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))` | > 500ms for 15min | warning |
| Postgres log: `remaining connection slots` | Any occurrence | critical |
| Sandbox concurrent count | > 10 sustained 5min | warning |
| `node_cpu_seconds_total` (prod) idle | < 30% for 10min | warning |
| `node_memory_MemAvailable_bytes` (prod) | < 500MB for 10min | warning |

### Phase 2 → Phase 3

| Metric | Threshold | Alert Severity |
|--------|-----------|---------------|
| Sandbox queue depth | > 10 sustained 5min | warning |
| `node_cpu_seconds_total` (prod) idle | < 20% for 10min | warning |
| Concurrent sandbox executions | > 30 sustained 5min | warning |
| Monthly execution count growth | > 50% month-over-month for 2 months | info |

### Phase 3 → Phase 4

| Metric | Threshold | Alert Severity |
|--------|-----------|---------------|
| Either API box CPU | > 80% sustained 10min | warning |
| Sandbox worker CPU | > 80% sustained 10min | warning |
| `prometheus_tsdb_head_series` | > 40,000 | warning |
| API p99 latency | > 500ms sustained 15min | warning |
| Postgres connection usage | > 70% of max | warning |

---

## What NOT to Do

### No Kubernetes Until 1,000+ Customers

K8s adds operational complexity that isn't justified at this scale. Two API boxes + a sandbox worker behind a DO load balancer achieves the same result with zero orchestration overhead. The team is small — operational simplicity wins.

**When K8s becomes worth it:** 1,000+ customers, 5+ services, need for auto-scaling, multiple engineering teams deploying independently.

### No Multi-Region Until Geographic Demand

Single-region (TOR1) serves all of North America with <50ms latency. Multi-region doubles infrastructure cost and adds data replication complexity.

**When multi-region becomes worth it:** Significant customer base in EU/APAC requiring data residency, or SLA requiring geographic redundancy.

### No Kafka

Redis Streams or Celery+Redis handles the task queue at this scale. Kafka's operational cost (broker cluster, ZooKeeper/KRaft, partition management) is wildly disproportionate to the workload.

**When Kafka becomes worth it:** 10,000+ events/second sustained, multi-consumer event streaming, event sourcing architecture.

### No Sharded Postgres

A single Postgres instance with read replicas handles the data volume at 500 customers comfortably. The tables are well-structured (UUIDs, timestamps, bounded relationships). Partitioning by month on high-volume tables is sufficient.

**When sharding becomes worth it:** Tens of millions of rows in hot tables, write throughput exceeding single-primary capacity.

### No Managed Container Services (App Platform, ECS)

DO App Platform and similar managed container services add cost and reduce control. Raw droplets with Docker Compose are cheaper, simpler to debug, and give full access to nsjail's Linux primitives (`--privileged`, `SYS_ADMIN`, `seccomp`). Managed container platforms often restrict these capabilities.

---

## Migration Checklists

### Phase 1 → Phase 2 Migration

```
□ Provision DO Managed Postgres (db-s-1vcpu-2gb, TOR1, private networking)
□ pg_dump from Docker Postgres, pg_restore to managed instance
□ Update DATABASE_URL in prod .env to managed Postgres connection string
□ Add PgBouncer container to docker-compose.prod.yml
□ Point API DATABASE_URL at PgBouncer (localhost:6432)
□ Reduce database_pool_size to 3, database_max_overflow to 5 in config
□ Provision DO Managed Redis (db-s-1vcpu-1gb, HA standby, TOR1)
□ Update REDIS_URL in prod .env to managed Redis connection string
□ Implement Redis fail-closed pattern in billing middleware
□ Remove postgres and redis containers from docker-compose.prod.yml
□ Resize prod droplet: s-2vcpu-4gb → s-4vcpu-8gb (requires downtime)
□ Verify health check passes
□ Run billing middleware integration test against managed Redis
□ Update Prometheus scrape targets (remove postgres/redis container metrics, add managed DB monitoring)
□ Update CLAUDE.md infrastructure section
```

### Phase 2 → Phase 3 Migration

```
□ Set up Celery with Redis broker (add celery to requirements.txt)
□ Create sandbox worker task module
□ Build sandbox worker Docker image (needs --privileged, nsjail)
□ Provision sandbox worker droplet (s-4vcpu-8gb, TOR1)
□ Deploy sandbox worker with docker-compose
□ Update SandboxBackend.execute() to enqueue tasks instead of local subprocess
□ Provision second API droplet (s-4vcpu-8gb, TOR1)
□ Deploy identical API stack to second droplet
□ Provision DO Load Balancer, add both API droplets as targets
□ Update DNS: api.mcpworks.io → LB IP
□ Update wildcard DNS: *.create.mcpworks.io, *.run.mcpworks.io → LB IP
□ Test health check failover (stop one API box, verify traffic routes to other)
□ Replace asyncio.create_task() fire-and-forget with Celery tasks for security events
□ Upgrade managed Postgres if connection count requires it
□ Update CI/CD to deploy to both API boxes and the sandbox worker
□ Update CLAUDE.md infrastructure section
```

---

## Relationship to PLAN.md

PLAN.md covers the **observability stack** (Grafana, Prometheus, Loki, Tempo, Uptime Kuma, Infisical) running on the mgmt droplet. This document covers **production infrastructure scaling**.

The two interact at these points:
- **Phase 2:** Prometheus scrape targets change (managed DB metrics via DO monitoring, not container metrics)
- **Phase 3:** New scrape targets (second API box, sandbox worker). Prometheus cardinality increases with additional instances.
- **Phase 4:** Prometheus → VictoriaMetrics migration on the mgmt droplet. Loki → DO Spaces backend for archival.

The mgmt droplet itself stays small until Phase 4, when the observability stack needs more headroom for the increased number of scrape targets and log streams.
