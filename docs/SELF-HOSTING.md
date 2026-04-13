# Self-Hosting MCPWorks

Deploy MCPWorks on your own Linux server with `docker compose up`.

## Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| OS | Linux (kernel 5.10+) | nsjail requires Linux namespaces. macOS/Windows: use `SANDBOX_DEV_MODE=true` (no code isolation) |
| Docker | 24.0+ | With Docker Compose v2 |
| RAM | 4 GB | 8 GB recommended for agent workloads |
| Disk | 20 GB | Plus storage for PostgreSQL data |
| Domain | A domain you control | With DNS access for wildcard records (subdomain routing) or a single A record (path routing) |
| Ports | 80, 443 open | For Caddy TLS certificate issuance |

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/MCPWorks-Technologies-Inc/mcpworks-api.git
cd mcpworks-api
```

### 2. Configure environment

```bash
cp .env.self-hosted.example .env
```

Edit `.env` and set at minimum:

```bash
# Your domain
BASE_DOMAIN=example.com

# Generate an encryption key
ENCRYPTION_KEK_B64=$(python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())")

# Admin account (must match ADMIN_EMAILS)
ADMIN_EMAILS=["admin@example.com"]

# Let's Encrypt notifications
ACME_EMAIL=admin@example.com
```

### 3. Generate JWT keys

```bash
mkdir -p keys
openssl ecparam -genkey -name prime256v1 -noout -out keys/private.pem
openssl ec -in keys/private.pem -pubout -out keys/public.pem
```

### 4. Configure DNS

**Path-based routing** (default, `ROUTING_MODE=path`) — only one record needed:

| Record | Type | Value |
|--------|------|-------|
| `api.example.com` | A | your server IP |

**Subdomain routing** (`ROUTING_MODE=subdomain`) — requires wildcard records:

| Record | Type | Value |
|--------|------|-------|
| `api.example.com` | A | your server IP |
| `*.create.example.com` | A | your server IP |
| `*.run.example.com` | A | your server IP |
| `*.agent.example.com` | A | your server IP |

Caddy obtains TLS certificates automatically via Let's Encrypt. Wildcard subdomain certificates use on-demand TLS — Caddy verifies each subdomain against the API's internal domain verification endpoint before issuing.

### 5. Start services

```bash
docker compose -f docker-compose.self-hosted.yml up -d
```

This starts four services:

| Service | Container | Purpose |
|---------|-----------|---------|
| PostgreSQL 15 | mcpworks-postgres | Primary database |
| Redis 7 | mcpworks-redis | Cache and rate limiting |
| API | mcpworks-api | MCPWorks backend (runs migrations on startup) |
| Caddy 2 | mcpworks-caddy | TLS termination and reverse proxy |

First startup takes 10-20 minutes — Docker builds a multi-stage image that compiles nsjail from source, pre-installs sandbox packages (Python + Node.js), and sets up the execution environment.

On startup, the API container automatically:
1. Waits for database connectivity
2. Runs all pending Alembic migrations
3. Initializes the nsjail sandbox environment (if not in dev mode)
4. Starts the uvicorn server

### 6. Verify

```bash
curl https://api.example.com/v1/health
```

Expected response: `{"status": "ok", ...}`

### 7. Create admin account

```bash
docker compose -f docker-compose.self-hosted.yml exec \
  -e ADMIN_EMAIL=admin@example.com \
  -e ADMIN_PASSWORD=changeme \
  api python3 scripts/seed_admin.py
```

The email must be in your `ADMIN_EMAILS` list for admin panel access. Change the password immediately after first login.

### 8. Connect from Claude Desktop

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "mcpworks": {
      "url": "https://api.example.com/mcp/create/your-namespace",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

## Configuration Reference

### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://mcpworks:mcpworks_selfhost@postgres:5432/mcpworks` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `JWT_PRIVATE_KEY_PATH` | Path to EC private key | `/app/keys/private.pem` |
| `JWT_PUBLIC_KEY_PATH` | Path to EC public key | `/app/keys/public.pem` |
| `ENCRYPTION_KEK_B64` | Base64-encoded 32-byte key for envelope encryption | (generate as shown above) |
| `BASE_DOMAIN` | Your domain | `example.com` |

### Recommended Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ACME_EMAIL` | `admin@localhost` | Email for Let's Encrypt certificate notifications |
| `ADMIN_EMAILS` | `[]` | JSON array of admin email addresses |
| `ALLOW_REGISTRATION` | `false` | Enable public user registration |

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_SCHEME` | `https` | URL scheme (`http` for local dev without TLS) |
| `ROUTING_MODE` | `path` | `path` (recommended), `subdomain`, or `both` |
| `APP_ENV` | `production` | Environment name |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CORS_ORIGINS` | derived from `BASE_DOMAIN` | Allowed CORS origins (JSON array) |
| `SANDBOX_DEV_MODE` | `true` | `false` for production nsjail isolation, `true` for subprocess fallback (dev only) |
| `UVICORN_WORKERS` | `1` | Number of uvicorn worker processes |
| `APP_PORT` | `8000` | API listen port inside the container |

### Email (optional)

Without email configured, the platform works normally — users just won't receive welcome emails or notifications.

**SMTP:**

| Variable | Description |
|----------|-------------|
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP port (typically 587) |
| `SMTP_USERNAME` | SMTP auth username |
| `SMTP_PASSWORD` | SMTP auth password |
| `SMTP_FROM_EMAIL` | Sender address |
| `SMTP_USE_TLS` | Enable STARTTLS (default: true) |

### Billing (optional)

Without Stripe configured, all users operate without execution limits. The billing middleware is bypassed entirely.

| Variable | Description |
|----------|-------------|
| `STRIPE_SECRET_KEY` | Stripe API secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |

## Sandbox Security Modes

MCPWorks executes user-submitted code (Python and TypeScript) in a sandbox. Two modes are available:

### nsjail (production)

Set `SANDBOX_DEV_MODE=false` in your `.env`. Provides full Linux namespace isolation:
- Separate PID, network, mount, and user namespaces
- Seccomp syscall filtering (allowlist-only)
- Memory and CPU limits via cgroups
- No filesystem access outside the sandbox
- `execve` blocked — user code cannot spawn processes
- Pre-installed Python and Node.js packages available inside the sandbox

**Requirements:** Linux kernel 5.10+, the container runs with `privileged: true` and `CAP_SYS_ADMIN`. User code runs as UID 65534 (nobody) inside nsjail with all capabilities dropped.

**Network isolation by tier:**
- **Free tier:** nsjail creates an empty network namespace — zero connectivity
- **Paid tiers:** A veth pair with NAT provides internet access while blocking internal networks (169.254.0.0/16, 172.16.0.0/12, 10.0.0.0/8, 192.168.0.0/16)

### SANDBOX_DEV_MODE (development only)

Set `SANDBOX_DEV_MODE=true` (the default) to use a subprocess fallback instead of nsjail. This works on macOS and Windows but provides **no code isolation**. User code runs with the same permissions as the API process.

**Use only for local development and evaluation. Never use in production.**

## Routing Modes

MCPWorks supports two URL routing patterns:

### Path-based (recommended)

`ROUTING_MODE=path` — all traffic goes through `api.example.com`:

```
https://api.example.com/mcp/create/my-namespace
https://api.example.com/mcp/run/my-namespace
```

Simpler DNS setup — only one A record needed for `api.example.com`.

### Subdomain-based

`ROUTING_MODE=subdomain` — each namespace gets its own subdomain:

```
https://my-namespace.create.example.com/mcp
https://my-namespace.run.example.com/mcp
```

Requires wildcard DNS records for `*.create`, `*.run`, and `*.agent`. Caddy uses on-demand TLS to issue certificates for each subdomain as it is first accessed.

### Both

`ROUTING_MODE=both` — accepts both patterns. Useful during migration.

## Agent Runtime (optional)

The docker-compose file mounts the Docker socket (`/var/run/docker.sock`) into the API container to support the agent runtime feature. Agents run as separate containers on the `mcpworks-agents` bridge network.

If you don't use agents, you can remove the Docker socket mount from `docker-compose.self-hosted.yml`:

```yaml
# Remove this line from the api service volumes:
- /var/run/docker.sock:/var/run/docker.sock
```

If you do use agents, ensure the Docker daemon is accessible and the `mcpworks-agents` network can be created.

## Using External Services

The self-hosted compose bundles PostgreSQL and Redis for convenience. To use existing instances:

1. Update `DATABASE_URL` in `.env` to point to your PostgreSQL server
2. Update `REDIS_URL` in `.env` to point to your Redis server
3. Remove the `postgres` and/or `redis` services from `docker-compose.self-hosted.yml`
4. Remove the corresponding `depends_on` entries from the `api` service

For managed PostgreSQL with SSL, the database module auto-enables SSL for non-localhost hosts.

For managed Redis with TLS, use `rediss://` (double s) in `REDIS_URL`.

## Observability

MCPWorks exposes a Prometheus-compatible metrics endpoint at `/metrics`. Connect Prometheus and Grafana for full operational visibility.

### Prometheus Setup

Add MCPWorks as a scrape target in your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "mcpworks"
    scrape_interval: 15s
    static_configs:
      - targets: ["api.example.com"]
    scheme: https
```

For self-hosted compose deployments where Prometheus runs on the same network, scrape the API container directly:

```yaml
scrape_configs:
  - job_name: "mcpworks"
    scrape_interval: 15s
    static_configs:
      - targets: ["mcpworks-api:8000"]
    metrics_path: /metrics
```

### Available Metrics

#### HTTP (automatic via FastAPI instrumentator)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, endpoint, status | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, endpoint | Request latency |
| `http_requests_inprogress` | Gauge | method, endpoint | In-flight requests |

#### Sandbox Execution

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sandbox_executions_total` | Counter | tier, status, namespace | Total sandbox executions |
| `sandbox_execution_duration_seconds` | Histogram | tier, status | Sandbox execution latency |
| `sandbox_executions_in_progress` | Gauge | tier | Active sandbox executions |
| `sandbox_execution_errors_total` | Counter | tier, error_type | Sandbox errors by type |
| `sandbox_violations_total` | Counter | tier | Seccomp/resource violations |

#### Agent Orchestration

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcpworks_agent_runs_total` | Counter | namespace, trigger_type, status | Agent orchestration runs |
| `mcpworks_agent_run_duration_seconds` | Histogram | namespace, trigger_type | Agent run duration |
| `mcpworks_agent_run_iterations_total` | Counter | namespace | AI loop iterations |
| `mcpworks_agent_tool_calls_total` | Counter | namespace, tool_name, source, status | Tool calls during orchestration |
| `mcpworks_agent_tool_call_duration_seconds` | Histogram | namespace, source | Per-tool-call latency |
| `mcpworks_agents_running` | Gauge | namespace | Active orchestrations |

#### MCP Proxy

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcpworks_mcp_proxy_calls_total` | Counter | namespace, server_name, tool_name, status | Proxy calls to external MCP servers |
| `mcpworks_mcp_proxy_latency_seconds` | Histogram | namespace, server_name | Proxy call latency |
| `mcpworks_mcp_proxy_response_bytes` | Histogram | namespace, server_name | Proxy response size |
| `mcpworks_mcp_proxy_injections_total` | Counter | namespace, server_name | Prompt injection detections |
| `mcpworks_mcp_proxy_truncations_total` | Counter | namespace, server_name | Truncated responses |

#### Per-Function

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcpworks_function_calls_total` | Counter | namespace, service, function, status | Function executions by name |
| `mcpworks_function_duration_seconds` | Histogram | namespace, service, function | Function execution duration |

#### MCP Transport (tool-level)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcpworks_mcp_tool_calls_total` | Counter | endpoint_type, tool_name | MCP tool invocations |
| `mcpworks_mcp_response_bytes` | Histogram | endpoint_type, tool_name | MCP response size (token proxy) |

#### Auth, Billing, Security, Webhooks

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcpworks_auth_attempts_total` | Counter | method, status | Auth attempts (login, register, apikey, oauth) |
| `mcpworks_billing_quota_checks_total` | Counter | namespace, result | Billing quota checks (allowed/blocked) |
| `mcpworks_security_events_total` | Counter | event_type, severity | Security events by type and severity |
| `mcpworks_webhook_deliveries_total` | Counter | namespace, status | Telemetry webhook deliveries |
| `mcpworks_webhook_delivery_latency_seconds` | Histogram | namespace | Webhook delivery latency |

### Grafana Example Queries

**Request error rate (5xx)**:
```promql
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
```

**Sandbox execution p95 latency by tier**:
```promql
histogram_quantile(0.95, rate(sandbox_execution_duration_seconds_bucket[5m]))
```

**Agent run failure rate**:
```promql
sum(rate(mcpworks_agent_runs_total{status="failed"}[5m])) / sum(rate(mcpworks_agent_runs_total[5m]))
```

**Top 10 functions by error rate**:
```promql
topk(10,
  sum by (namespace, service, function) (rate(mcpworks_function_calls_total{status="error"}[1h]))
  / sum by (namespace, service, function) (rate(mcpworks_function_calls_total[1h]))
)
```

**MCP proxy latency p99 by server**:
```promql
histogram_quantile(0.99, sum by (le, server_name) (rate(mcpworks_mcp_proxy_latency_seconds_bucket[5m])))
```

**Auth failure spike alert** (Grafana alert rule):
```promql
sum(rate(mcpworks_auth_attempts_total{status="failure"}[5m])) > 0.5
```

### Structured Logging

All API logs are JSON-formatted via structlog. Each log line includes:
- `correlation_id` — unique per-request, propagated via `X-Request-ID` header
- `timestamp` — ISO 8601
- `level` — debug, info, warning, error
- `event` — structured event name

Pipe container logs to your preferred log aggregation tool (Loki, Elasticsearch, CloudWatch):

```bash
docker logs mcpworks-api --follow | jq .
```

### Health Endpoints

| Endpoint | Purpose | Use For |
|----------|---------|---------|
| `GET /v1/health` | Always returns `{"status": "healthy"}` | Load balancer health check |
| `GET /v1/health/live` | Always returns `{"status": "alive"}` | Kubernetes liveness probe |
| `GET /v1/health/ready` | Checks DB, Redis, sandbox | Kubernetes readiness probe |

### Audit Log

Security events (auth failures, sandbox violations, quota blocks, agent anomalies) are persisted to the `security_events` table with hashed IPs and PII-scrubbed details. Query via the admin API:

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://api.example.com/v1/audit/logs?severity=critical&limit=20
```

## Database Migrations

Migrations run automatically on container startup — the startup script (`scripts/start.sh`) runs `alembic upgrade head` before starting the API server. No manual intervention is needed for upgrades — pull the latest code, rebuild, and restart:

```bash
git pull
docker compose -f docker-compose.self-hosted.yml up -d --build api
```

## Upgrading

```bash
cd mcpworks-api
git pull origin main
docker compose -f docker-compose.self-hosted.yml up -d --build api
curl https://api.example.com/v1/health
```

Migrations run automatically on startup. Check container logs if health check fails:

```bash
docker logs mcpworks-api --tail 50
```

## Troubleshooting

### Health check fails on startup

The API has a 60-second startup grace period. If health checks still fail:

```bash
docker logs mcpworks-api --tail 100
```

Common causes:
- Missing `ENCRYPTION_KEK_B64` — generate one (see step 2)
- JWT keys not found — verify `keys/private.pem` and `keys/public.pem` exist
- Database connection refused — ensure PostgreSQL is healthy: `docker logs mcpworks-postgres`
- Missing migrations — the startup script runs them automatically, but check logs for Alembic errors

### Caddy fails to obtain TLS certificates

- Verify ports 80 and 443 are open and reachable from the internet
- Verify DNS records are pointing to your server
- Check Caddy logs: `docker logs mcpworks-caddy`
- Set `ACME_EMAIL` in `.env` for Let's Encrypt account registration
- For subdomain routing: on-demand TLS requires the API to be healthy (Caddy verifies domains against the API)

### Sandbox violations (exit code 159)

Exit code 159 = SIGSYS (seccomp violation). A syscall is blocked by the sandbox policy. Check:

```bash
sudo dmesg | grep audit | tail -10
```

The audit log shows the blocked syscall number. Report it as an issue if it's blocking legitimate Python/Node.js operations.

### "No module named 'functions'" in scheduled tasks

Ensure the scheduled function's `orchestration_mode` is not `direct` if the function code uses `from functions import ...`. Use `execute_only` or `reason_first` mode instead.

### Slow first build

The first Docker build compiles nsjail from source and installs sandbox packages for both Python and Node.js. This typically takes 10-20 minutes depending on hardware. Subsequent rebuilds are faster due to Docker layer caching.

### Local development without a domain

For local testing without DNS:

```bash
BASE_DOMAIN=localhost
BASE_SCHEME=http
ROUTING_MODE=path
SANDBOX_DEV_MODE=true
```

Remove the `caddy` service from compose and access the API directly on port 8000. You'll need to expose port 8000 on the api service:

```yaml
# In docker-compose.self-hosted.yml, change api service:
ports:
  - "8000:8000"
```

Then:

```bash
curl http://localhost:8000/v1/health
```
