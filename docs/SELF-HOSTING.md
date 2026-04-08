# Self-Hosting MCPWorks

Deploy MCPWorks on your own Linux server with `docker compose up`.

## Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| OS | Linux (kernel 5.10+) | nsjail requires Linux namespaces. macOS/Windows: use `SANDBOX_DEV_MODE=true` (no code isolation) |
| Docker | 24.0+ | With Docker Compose v2 |
| RAM | 4 GB | 8 GB recommended for agent workloads |
| Disk | 20 GB | Plus storage for PostgreSQL data |
| Domain | A domain you control | With DNS access for wildcard records |
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
```

### 3. Generate JWT keys

```bash
mkdir -p keys
openssl ecparam -genkey -name prime256v1 -noout -out keys/private.pem
openssl ec -in keys/private.pem -pubout -out keys/public.pem
```

### 4. Configure DNS

Point these records to your server's IP:

| Record | Type | Value |
|--------|------|-------|
| `api.example.com` | A | your server IP |
| `*.create.example.com` | A | your server IP |
| `*.run.example.com` | A | your server IP |
| `*.agent.example.com` | A | your server IP |

Caddy obtains TLS certificates automatically via Let's Encrypt. Set `ACME_EMAIL` in your `.env` for certificate expiry notifications.

### 5. Start services

```bash
docker compose -f docker-compose.self-hosted.yml up -d
```

This starts four services:

| Service | Container | Purpose |
|---------|-----------|---------|
| PostgreSQL 15 | mcpworks-postgres | Primary database |
| Redis 7 | mcpworks-redis | Cache and rate limiting |
| API | mcpworks-api | MCPWorks backend |
| Caddy 2 | mcpworks-caddy | TLS termination and reverse proxy |

First startup takes 5-10 minutes (Docker builds the API image including nsjail compilation).

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

The email must be in your `ADMIN_EMAILS` list for admin panel access.

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

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_SCHEME` | `https` | URL scheme (`http` for local dev without TLS) |
| `ROUTING_MODE` | `path` | `path` (recommended), `subdomain`, or `both` |
| `ALLOW_REGISTRATION` | `false` | Enable public user registration |
| `APP_ENV` | `production` | Environment name |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CORS_ORIGINS` | derived from `BASE_DOMAIN` | Allowed CORS origins (JSON array) |
| `SANDBOX_DEV_MODE` | `false` | Use subprocess instead of nsjail (no isolation, dev only) |

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

MCPWorks executes user-submitted code in a sandbox. Two modes are available:

### nsjail (production)

The default. Provides full Linux namespace isolation:
- Separate PID, network, mount, and user namespaces
- Seccomp syscall filtering (allowlist-only)
- Memory and CPU limits via cgroups
- No filesystem access outside the sandbox
- `execve` blocked — user code cannot spawn processes

**Requirements:** Linux kernel 5.10+, the container runs with `privileged: true` and `CAP_SYS_ADMIN`. User code runs as UID 65534 (nobody) inside nsjail with all capabilities dropped.

### SANDBOX_DEV_MODE (development only)

Set `SANDBOX_DEV_MODE=true` to use a subprocess fallback instead of nsjail. This works on macOS and Windows but provides **no code isolation**. User code runs with the same permissions as the API process.

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

Requires wildcard DNS records for `*.create`, `*.run`, and `*.agent`.

### Both

`ROUTING_MODE=both` — accepts both patterns. Useful during migration.

## Using External Services

The self-hosted compose bundles PostgreSQL and Redis for convenience. To use existing instances:

1. Update `DATABASE_URL` in `.env` to point to your PostgreSQL server
2. Update `REDIS_URL` in `.env` to point to your Redis server
3. Remove the `postgres` and/or `redis` services from `docker-compose.self-hosted.yml`
4. Remove the corresponding `depends_on` entries from the `api` service

For managed PostgreSQL with SSL, the database module auto-enables SSL for non-localhost hosts.

For managed Redis with TLS, use `rediss://` (double s) in `REDIS_URL`.

## Database Migrations

Migrations run automatically on container startup via Alembic. No manual intervention is needed for upgrades — pull the latest code, rebuild, and restart:

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

Migrations run automatically. Check container logs if health check fails:

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

### Caddy fails to obtain TLS certificates

- Verify ports 80 and 443 are open and reachable from the internet
- Verify DNS records are pointing to your server
- Check Caddy logs: `docker logs mcpworks-caddy`
- Set `ACME_EMAIL` in `.env` for Let's Encrypt account registration

### Sandbox violations (exit code 159)

Exit code 159 = SIGSYS (seccomp violation). A syscall is blocked by the sandbox policy. Check:

```bash
sudo dmesg | grep audit | tail -10
```

The audit log shows the blocked syscall number. Report it as an issue if it's blocking legitimate Python/Node.js operations.

### "No module named 'functions'" in scheduled tasks

Ensure the scheduled function's `orchestration_mode` is not `direct` if the function code uses `from functions import ...`. Use `execute_only` or `reason_first` mode instead.

### Local development without a domain

For local testing without DNS:

```bash
BASE_DOMAIN=localhost
BASE_SCHEME=http
ROUTING_MODE=path
```

Remove the `caddy` service from compose and access the API directly on port 8000:

```bash
curl http://localhost:8000/v1/health
```
