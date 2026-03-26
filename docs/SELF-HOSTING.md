# Self-Hosting MCPWorks

Deploy MCPWorks on your own infrastructure. This guide takes you from a fresh Linux server to a running instance.

## Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| OS | Linux (kernel 5.10+) | macOS/Windows for evaluation only |
| Docker | 24.0+ | With Docker Compose v2 |
| RAM | 2 GB | 4 GB recommended |
| Disk | 20 GB | SSD recommended |
| Domain | Wildcard DNS | Required for namespace subdomains |
| Ports | 80, 443 | Must be open for Let's Encrypt |

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/MCPWorks-Technologies-Inc/mcpworks-api.git
cd mcpworks-api

# 2. Create environment file
cp .env.self-hosted.example .env

# 3. Generate JWT key files
mkdir -p keys
openssl ecparam -genkey -name prime256v1 -noout -out keys/private.pem
openssl ec -in keys/private.pem -pubout -out keys/public.pem

# 4. Generate encryption key and set it in .env
KEK=$(python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())")
echo "Generated key: $KEK"
# Edit .env and set ENCRYPTION_KEK_B64=<the generated key>

# 5. Set your domain in .env
# Edit BASE_DOMAIN=yourdomain.com

# 6. Start all services
docker compose -f docker-compose.self-hosted.yml up -d

# 7. Wait for health check
curl https://api.yourdomain.com/v1/health

# 8. Create admin account
# Set ADMIN_EMAIL and ADMIN_PASSWORD in .env first, or the script will use defaults
docker exec mcpworks-api python3 scripts/seed_admin.py
```

## DNS Configuration

MCPWorks uses wildcard subdomains for namespace routing. Configure these DNS records:

| Record | Type | Value |
|--------|------|-------|
| `api.yourdomain.com` | A | Your server IP |
| `*.create.yourdomain.com` | A | Your server IP |
| `*.run.yourdomain.com` | A | Your server IP |
| `*.agent.yourdomain.com` | A | Your server IP |

Caddy automatically provisions TLS certificates via Let's Encrypt for each subdomain on first access.

## Configuration Reference

### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `BASE_DOMAIN` | Your domain name | `example.com` |
| `JWT_PRIVATE_KEY_PATH` | Path to ES256 private key file | `/app/keys/private.pem` |
| `JWT_PUBLIC_KEY_PATH` | Path to ES256 public key file | `/app/keys/public.pem` |
| `ENCRYPTION_KEK_B64` | 32-byte key (base64) | Output of keygen command |

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_SCHEME` | `https` | Use `http` for local dev without TLS |
| `ALLOW_REGISTRATION` | `false` | Set `true` to allow public signup |
| `ADMIN_EMAIL` | - | Email for seed admin account |
| `ADMIN_PASSWORD` | - | Password for seed admin account |
| `STRIPE_SECRET_KEY` | (empty) | Enable billing when set |
| `RESEND_API_KEY` | (empty) | Enable Resend email when set |
| `SMTP_HOST` | (empty) | Enable SMTP email when set |
| `SANDBOX_DEV_MODE` | `true` | Set `false` for production (requires Linux) |

See `.env.self-hosted.example` for the complete list with descriptions.

## Sandbox Security Modes

MCPWorks uses nsjail to isolate user code execution. There are two modes:

### Production Mode (`SANDBOX_DEV_MODE=false`)

- Uses nsjail with Linux namespaces, cgroups v2, and seccomp-bpf
- Full process isolation — user code cannot access the host
- **Requires Linux** with kernel 5.10+ and privileged Docker container
- Recommended for any deployment running untrusted code

### Dev Mode (`SANDBOX_DEV_MODE=true`)

- Uses Python subprocess — **no isolation**
- User code runs with the same permissions as the API process
- Works on macOS, Windows (WSL2), and Linux
- **Only use for evaluation or trusted code**

## Billing

By default, self-hosted instances run without billing. All users get unlimited executions.

To enable billing:
1. Create a Stripe account
2. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in `.env`
3. Configure Stripe price IDs for each tier
4. Restart the API container

## Email

Email is optional. Without it, users won't receive welcome emails or notifications, but all other functionality works.

**Option 1: Resend** — Set `RESEND_API_KEY` in `.env`

**Option 2: SMTP** — Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` in `.env`

**Option 3: Disabled** — Leave all email settings empty (emails are silently skipped)

## Using External Databases

The self-hosted compose file includes PostgreSQL and Redis. To use your own:

1. Set `DATABASE_URL` to your PostgreSQL connection string
2. Set `REDIS_URL` to your Redis connection string
3. Remove the `postgres` and `redis` services from `docker-compose.self-hosted.yml`

## Upgrading

```bash
cd mcpworks-api
git pull origin main
docker compose -f docker-compose.self-hosted.yml build api
docker compose -f docker-compose.self-hosted.yml up -d api
```

Migrations run automatically on container startup.

## Troubleshooting

### Health check fails

```bash
docker logs mcpworks-api --tail 50
```

Common causes:
- Database not ready (wait for postgres healthcheck)
- JWT keys not set or malformed
- Port 8000 not accessible from Caddy

### Caddy certificate errors

- Ensure ports 80 and 443 are open to the internet
- Ensure DNS records are pointing to your server
- Check Caddy logs: `docker logs mcpworks-caddy --tail 50`

### nsjail errors

- Ensure `SANDBOX_DEV_MODE=false` is set
- Container must run with `privileged: true`
- Host kernel must support namespaces and cgroups v2
- Check: `docker exec mcpworks-api nsjail --help`

### Registration disabled

Self-hosted instances default to closed registration. To enable:
- Set `ALLOW_REGISTRATION=true` in `.env`
- Or create accounts manually via the seed script

## Architecture

```
Internet → Caddy (TLS) → MCPWorks API → PostgreSQL
                                       → Redis
                                       → nsjail (code sandbox)
```

All services run in Docker containers on a single machine. For high-availability deployments, see the project documentation.
