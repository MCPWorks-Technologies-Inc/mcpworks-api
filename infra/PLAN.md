# Management Infrastructure Plan

## Overview

A single DigitalOcean droplet (`mcpworks-mgmt`) running a self-hosted observability stack — metrics, logs, traces, uptime, and secrets management. Grafana is the sole interface, accessed via SSH tunnel. Think personal Datadog, open-source, $12-24/mo.

**Status:** Configs ready in `mgmt/`, `prod/`, `scripts/`. Not yet deployed.

## Architecture

```
              SSH Tunnel (dev machine)
                     |
              localhost:3000
                     |
              +-----------+
              |  Grafana  |  <-- Single entry point
              +-----------+
              / |    |     \
    Prometheus Loki Tempo  (Infinity plugin)
        |       ^     ^
   scrape x3    |     | OTLP
        |       |     |
  +-----+----+ |     |
  |     |    |  |     |
  API  Node  UK |     |
  /metrics   /metrics |
  :8000 :9100 :3001   |
  |                   |
  +-- structlog JSON -+-- promtail --> Loki
  +-- OpenTelemetry spans -----------> Tempo
  [----------- prod -----------]
```

## What Already Exists in the API

The codebase is well-instrumented. This isn't starting from zero:

| Feature | Status | Details |
|---------|--------|---------|
| `/metrics` endpoint | Done | `prometheus-fastapi-instrumentator` + custom MCP metrics |
| Structured logging | Done | structlog JSON with namespace, service, account_id, duration_ms |
| Correlation IDs | Done | `X-Request-ID` header, bound to all logs via ContextVar |
| Per-request logging | Done | Method, path, status, duration, namespace, endpoint_type, bytes |
| Execution tracking | Done | Execution model with status, timing, error scrubbing |
| Call counts | Done | `Namespace.call_count`, `NamespaceService.call_count`, `Function.call_count` |
| Security events | Done | SecurityEvent table, IP hashing, fire-and-forget |
| Audit logs | Done | Immutable AuditLog table |
| Usage/billing tracking | Done | Redis-based monthly quota per tier |
| Sentry (optional) | Done | `SENTRY_DSN` env var, 10% trace sample rate |
| OpenTelemetry | Not yet | No distributed tracing |

## Services

Upgrade to **s-2vcpu-4gb** ($24/mo) to fit the full stack comfortably.

| Service | Port | mem_limit | Purpose |
|---------|------|-----------|---------|
| Grafana | 3000 | 512m | Dashboards, Explore, alerting |
| Prometheus | 9090 | 1024m | Metrics (14d retention) |
| Loki | 3100 | 768m | Logs (7d retention) |
| Tempo | 3200 | 384m | Traces (3d retention) |
| Uptime Kuma | 3001 | 128m | Uptime monitoring, SSL certs |
| Infisical | 9080 | 384m | Secrets management |
| Infisical DB | 5432 | 256m | Infisical backing store |
| Infisical Redis | 6379 | 64m | Infisical cache |
| **Total** | | **3,520m** | Fits s-2vcpu-4gb (~500m for OS) |

## Hard Limits (4GB droplet, shared stack)

| Constraint | Ceiling | Target |
|------------|---------|--------|
| Prometheus active series | 50,000 | Under 30,000 |
| Loki active streams | 10,000 | Under 5,000 |
| Loki comfortable query range | 6 hours | Default 1 hour |
| Log ingestion rate | 3-5 MB/s | Under 2 MB/s |
| Prometheus scrape interval | 15-60s | 30s |
| Dashboard panels per page | 30 max | 15-20 |
| Total monitoring disk | ~25 GB | 10 GB cap |

---

## Application Metrics (Prometheus)

### What Gets Scraped

| Job | Target | Interval | Metrics |
|-----|--------|----------|---------|
| mcpworks-api | PROD_VPC_IP:8000 | 30s | HTTP RED, custom app metrics |
| node-exporter | PROD_VPC_IP:9100 | 30s | CPU, memory, disk, network |
| uptime-kuma | uptime-kuma:3001 | 30s | Uptime, response times, SSL certs |

### Existing Prometheus Metrics (already exported)

- `http_requests_total{method, endpoint, status}` — request counter
- `http_request_duration_seconds{method, endpoint}` — latency histogram
- `http_requests_inprogress` — in-flight gauge
- `mcpworks_mcp_tool_calls_total{endpoint_type, tool_name}` — MCP tool invocations
- `mcpworks_mcp_response_bytes` — response size histogram (token proxy)
- `mcpworks_env_passthrough_requests_total` — env passthrough counter
- `mcpworks_env_passthrough_vars_count` — env vars per request
- `mcpworks_env_passthrough_errors_total{type}` — validation errors

### New Metrics to Add

```python
# Namespace/service-level execution metrics
mcpworks_function_executions_total{namespace, service, status}   # Counter
mcpworks_function_duration_seconds{namespace, service, status}   # Histogram
mcpworks_function_errors_total{namespace, service, error_type}   # Counter

# Billing/quota
mcpworks_namespace_usage_ratio{namespace}                        # Gauge (0.0-1.0)
mcpworks_billing_quota_exceeded_total{namespace}                 # Counter

# Sandbox
mcpworks_sandbox_setup_seconds{namespace}                        # Histogram
mcpworks_sandbox_violations_total{violation_type}                # Counter
```

### Cardinality Design (critical)

**Labels that go on Prometheus metrics (low cardinality, indexed):**
- `namespace` — bounded, grows with customers
- `service` — bounded per namespace (~10 max)
- `status` — 3 values: success, error, timeout
- `error_type` — <10 values: validation, runtime, timeout, quota

**Data that stays in logs only (high cardinality, NOT Prometheus labels):**
- `function` — 50 per service, too many combinations
- `request_id` — unbounded
- `user_id` — unbounded
- `account_id` — unbounded

**Budget at scale:**

| Scale | Namespace metrics | Service metrics | Infra | Total |
|-------|------------------|-----------------|-------|-------|
| 100 namespaces | 1,200 series | 6,000 series | 750 | ~8,000 |
| 500 namespaces | 6,000 series | 30,000 series | 750 | ~37,000 |
| 1,000+ namespaces | Drop service label, use Loki | | | |

### Recording Rules

Pre-aggregate expensive queries to keep dashboards fast:

```yaml
groups:
  - name: mcpworks_aggregations
    interval: 30s
    rules:
      - record: mcpworks:executions:rate5m_by_namespace
        expr: sum by (namespace, status) (rate(mcpworks_function_executions_total[5m]))
      - record: mcpworks:error_rate:ratio_5m
        expr: |
          sum by (namespace) (rate(mcpworks_function_executions_total{status="error"}[5m]))
          / sum by (namespace) (rate(mcpworks_function_executions_total[5m]))
      - record: mcpworks:latency:p99_5m
        expr: histogram_quantile(0.99, sum by (namespace, le) (rate(mcpworks_function_duration_seconds_bucket[5m])))
```

---

## Log Exploration (Loki) — The "Personal Datadog" Layer

Loki doesn't index log content (unlike Datadog/Elasticsearch). It indexes labels and greps content at query time. This means: label filtering is instant, content searching scales with time range.

### Loki Label Strategy

```
Labels (indexed, fast):
  job       = "mcpworks-api"
  namespace = "acme-corp"         # Yes — bounded
  level     = "info"              # Yes — 5 values

NOT labels (parsed at query time with | json):
  service, function, request_id, duration_ms, account_id, error_type
```

100 namespaces x 5 levels = 500 streams. At 1,000 namespaces = 5,000 streams. Both fine.

### What the Logs Already Contain

Every request emits one structlog JSON line:
```json
{
  "timestamp": "2026-03-01T12:00:00Z",
  "level": "info",
  "event": "request_completed",
  "method": "POST",
  "path": "/mcp",
  "status": 200,
  "duration_ms": 142,
  "namespace": "acme-corp",
  "endpoint_type": "run",
  "account_id": "acc_abc123",
  "request_bytes": 1024,
  "response_bytes": 512,
  "correlation_id": "req_xyz789"
}
```

### Key LogQL Queries

```logql
# All logs for a namespace
{namespace="acme-corp"}

# Errors for a specific service
{namespace="acme-corp", level="error"} | json | service="payment-api"

# Find a specific request by correlation ID
{namespace="acme-corp"} |= "req_xyz789"

# Parse JSON and filter on function
{namespace="acme-corp"} | json | function_name="process_payment" | duration_ms > 500

# Function-level metrics FROM LOGS (the key insight — no Prometheus cardinality needed)
topk(10,
  avg by (function_name) (
    {namespace="acme-corp"} | json | unwrap duration_ms | __error__=""
  )
)

# Error rate by namespace as a metric
sum by (namespace) (rate({level="error"}[5m]))

# Count by error type over last hour
sum by (error_type) (count_over_time({namespace="acme-corp", level="error"} | json[1h]))
```

### Loki Tuning for Small Droplet

```yaml
limits_config:
  retention_period: 168h              # 7 days
  max_query_series: 500
  max_query_parallelism: 2
  max_entries_limit_per_query: 5000
  ingestion_rate_mb: 4
  ingestion_burst_size_mb: 8
  per_stream_rate_limit: 3MB
  max_streams_per_user: 10000

ingester:
  chunk_idle_period: 1h
  chunk_encoding: snappy
```

---

## Tracing (Tempo) — Phase 3

Not day-one, but valuable even for a single service. Function executions pass through multiple stages (auth, quota check, sandbox setup, code execution, result capture). A trace shows the waterfall:

```
execute_function [total: 340ms]
  |-- check_quota [12ms]
  |-- setup_sandbox [180ms]  <-- immediately obvious bottleneck
  |-- run_code [142ms]
```

### Implementation

Add OpenTelemetry instrumentation to the FastAPI app:

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import trace

FastAPIInstrumentor.instrument_app(app)
tracer = trace.get_tracer("mcpworks-api")
```

Tempo receives spans via OTLP (port 4317/4318), stores 3 days, and feeds span metrics back to Prometheus — reducing the need for manual metric instrumentation.

### Log-to-Trace Correlation

Configure Loki derived fields in Grafana so clicking a log line opens the trace:

```yaml
derivedFields:
  - name: TraceID
    matcherRegex: '"trace_id":"(\w+)"'
    url: '${__value.raw}'
    datasourceUid: tempo
```

### Tempo Resource Budget

| Component | RAM | Disk (3d, ~100 req/s) |
|-----------|-----|------------------------|
| Tempo | 200-400m | 500m - 2 GB |

Lightest of the three backends — append-only storage, minimal indexing.

---

## Grafana Dashboards

### Existing (ready to deploy)

1. **System Overview** — CPU, memory, disk, network, load average, filesystem free
2. **mcpworks API** — Request rate, error rate, p95 latency, status codes, in-progress requests, top endpoints

### To Build

3. **Uptime Kuma** — Import community dashboard [ID 18278](https://grafana.com/grafana/dashboards/18278-uptime-kuma/)

4. **Operations Overview (Home)** — Set as Grafana home dashboard

| Row | Panels | Source |
|-----|--------|--------|
| Service Health | Stat: UP/DOWN for API, Infisical, Grafana, Prometheus, Loki | Uptime Kuma -> Prometheus |
| API Metrics | Request rate, error rate, p95 latency, active connections | mcpworks-api -> Prometheus |
| System Resources | CPU, memory, disk, network | node-exporter -> Prometheus |
| Uptime SLA | 7d/30d uptime %, response time graph | Uptime Kuma -> Prometheus |
| Recent Errors | Last 20 error/warning log lines | Loki |
| SSL Certificates | Days until expiry per domain | Uptime Kuma -> Prometheus |

5. **Namespace Explorer** — Drill-down dashboard with template variables

```
Variables:
  $namespace -> label_values(mcpworks_function_executions_total, namespace)
  $service   -> Loki query: unique services for $namespace
  $timerange -> built-in Grafana time picker

Row 1: Overview (all namespaces)
  - Total executions/min (stat)
  - Error rate % (gauge, red > 5%)
  - P99 latency (stat)
  - Active namespaces (stat)

Row 2: Namespace Detail ($namespace selected)
  - Executions over time by status (time series)
  - Error rate over time (time series)
  - Latency distribution (heatmap)
  - Top errors (table from Loki)

Row 3: Service Detail ($namespace + $service)
  - Function-level metrics (Loki metric queries)
  - Recent errors (log panel)
  - Latency histogram

Row 4: Logs
  - Filtered log panel: {namespace="$namespace"} | json
```

6. **Monitoring Health** — The stack monitoring itself

```promql
process_resident_memory_bytes{job="prometheus"} / 1024 / 1024  # Prometheus RAM
prometheus_tsdb_head_series                                      # Cardinality canary
loki_distributor_bytes_received_total                             # Loki ingestion rate
```

### Grafana Plugins to Install

| Plugin | Purpose |
|--------|---------|
| grafana-piechart-panel | Usage breakdown by namespace |
| grafana-polystat-panel | Multi-namespace status grid |
| grafana-json-datasource | Query the API for billing/subscription data |
| yesoreyeram-infinity-datasource | Flexible REST/JSON/CSV datasource |

### Deployment Annotations

Add to CI/CD (deploy.yml) — creates vertical lines on dashboards correlating deploys with metrics changes:

```bash
curl -X POST http://grafana:3000/api/annotations \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -d '{"dashboardUID":"mcpworks-overview","text":"Deploy: '$GITHUB_SHA'","tags":["deploy"]}'
```

---

## Alert Rules

### Infrastructure (existing)

| Alert | Condition | Severity |
|-------|-----------|----------|
| InstanceDown | Any target `up == 0` for 2m | critical |
| ApiDown | mcpworks-api unreachable for 1m | critical |
| HighCpuUsage | CPU > 80% for 5m | warning |
| HighMemoryUsage | Memory > 85% for 5m | warning |
| DiskSpaceLow | Disk free < 15% for 5m | warning |
| HighErrorRate | 5xx > 5% of requests for 5m | warning |
| HighLatency | P95 > 1s for 5m | warning |

### Application (new, via Grafana Unified Alerting)

| Alert | Condition | Severity |
|-------|-----------|----------|
| NamespaceHighErrorRate | `mcpworks:error_rate:ratio_5m > 0.05` for 5m | warning |
| NamespaceHighLatency | `mcpworks:latency:p99_5m > 5s` for 5m | warning |
| QuotaApproaching | `mcpworks_namespace_usage_ratio > 0.9` for 10m | info |
| SandboxViolationSpike | `rate(mcpworks_sandbox_violations_total[5m]) > 1` for 5m | warning |
| CardinalityCreep | `prometheus_tsdb_head_series > 30000` | warning |

Notifications: Slack webhook + email.

---

## Bottleneck Progression (what breaks first)

1. **Loki query performance on wide time ranges** — Querying >24h with JSON parsing at >50 logs/sec. Mitigation: narrow time ranges, set `max_query_length: 24h`.
2. **Prometheus memory from cardinality** — >50K active series OOMKills Prometheus. Mitigation: monitor `prometheus_tsdb_head_series`, alert at 30K.
3. **Disk exhaustion** — ~500m-1GB/day across all components. Mitigation: size-based retention caps.
4. **Dashboard rendering** — >30 panels or >100 series per panel. Mitigation: use variables, link between dashboards.
5. **Prometheus compaction CPU** — Periodic spikes every 2h. Mitigation: `--storage.tsdb.max-block-duration=24h`.

---

## Retention Budget

| Component | Retention | Disk (estimated) |
|-----------|-----------|------------------|
| Prometheus (20K series) | 14 days | ~2 GB |
| Loki (50 logs/sec) | 7 days | ~3 GB |
| Tempo (100 req/sec) | 3 days | ~1 GB |
| **Total** | | **~6 GB** |

---

## Infisical

Accessed directly at `localhost:9080` via SSH tunnel for secret rotation (rare).

**In Grafana:** health check indicator (green/red) via Uptime Kuma HTTP monitor.

**Migration path:** Run `scripts/migrate-secrets.sh` to move prod `.env` values into Infisical, then set `INFISICAL_TOKEN` + `INFISICAL_PROJECT_ID` on prod. API's `scripts/start.sh` already supports `infisical run`.

---

## Prod-Side Components

Deployed via `prod/deploy-exporters.sh`:

- **node-exporter** — Host metrics. Bound to VPC IP only.
- **promtail** — Ships Docker logs + syslog to Loki. Extracts `level` and `event` labels from structlog JSON.

---

## Deployment Phases

### Phase 1: Infrastructure Monitoring

1. Provision mgmt droplet: `./infra/scripts/provision-mgmt-droplet.sh`
2. Deploy mgmt stack: `./infra/mgmt/deploy.sh <mgmt-vpc-ip> <prod-public-ip> <prod-vpc-ip>`
3. Deploy prod exporters: `./infra/prod/deploy-exporters.sh <prod-public-ip> <mgmt-vpc-ip>`
4. Configure Uptime Kuma monitors, enable Prometheus export
5. Build Operations Overview home dashboard

**Result:** System metrics, uptime monitoring, basic API RED metrics, log tailing.

### Phase 2: Application Observability

6. Add namespace/service-level Prometheus metrics to the API
7. Update promtail to extract `namespace` as a Loki label
8. Add Prometheus recording rules for pre-aggregation
9. Build Namespace Explorer drill-down dashboard
10. Configure application-level alerts (error rate, latency, quota)
11. Set up Grafana Explore for ad-hoc log searching
12. Add deployment annotations to CI/CD

**Result:** Full namespace/service drill-down, log exploration, alerting on business metrics.

### Phase 3: Distributed Tracing

13. Add Tempo to mgmt docker-compose
14. Add OpenTelemetry instrumentation to the FastAPI app
15. Configure log-to-trace correlation in Grafana
16. Enable Tempo span metrics -> Prometheus
17. Build trace-aware panels in dashboards

**Result:** Click-through from log line to full request trace waterfall. Automatic RED metrics from spans.

### Phase 4: Secrets Management

18. Migrate secrets to Infisical
19. Configure machine identity for prod
20. Switch API to Infisical-backed env injection

**Result:** Centralized secret rotation, audit trail for secret access.

---

## Changes Needed Before Deploy

1. **Upgrade droplet size** in `scripts/provision-mgmt-droplet.sh`: `s-1vcpu-2gb` -> `s-2vcpu-4gb`
2. **Add Tempo** to `mgmt/docker-compose.yml`
3. **Add Uptime Kuma Prometheus scrape** to `mgmt/prometheus/prometheus.yml`
4. **Add recording rules** to `mgmt/prometheus/prometheus.yml`
5. **Update Loki config** — tighten retention to 7d, add stream limits
6. **Update Prometheus config** — 30s scrape interval, 14d retention, WAL compression
7. **Update Grafana mem_limit** — 256m -> 512m
8. **Download Uptime Kuma dashboard** JSON
9. **Build Operations Overview + Namespace Explorer** dashboards
10. **Set `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH`** in Grafana environment

---

## Access

All via SSH tunnel:

```bash
./infra/scripts/tunnel.sh <mgmt-vpc-ip> <prod-public-ip>
```

| URL | Service |
|-----|---------|
| http://localhost:3000 | Grafana (primary — everything lives here) |
| http://localhost:9080 | Infisical (secret rotation only) |
| http://localhost:9090 | Prometheus (direct query, rarely needed) |
| http://localhost:3001 | Uptime Kuma (native UI, rarely needed) |

---

## Priority

Lower priority but important. Deploy when:
- Production API is stable and generating real traffic worth monitoring
- Secret rotation frequency justifies Infisical over manual `.env` management
- Uptime SLA commitments exist (paying customers)

Phase 1 is ~half a day of work. Phases 2-4 can be incremental.
