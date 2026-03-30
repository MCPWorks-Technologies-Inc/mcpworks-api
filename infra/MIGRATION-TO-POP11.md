# Migration: DO Cloud to POP11 On-Prem

**Date:** 2026-03-30
**Goal:** Move all MCPWorks services to server0.pop11, reduce api.mcpworks.io to edge proxy.

## Architecture

```
[INTERNET]
     |
api.mcpworks.io (159.203.30.199)    <-- Caddy only, TLS + reverse proxy
     | WireGuard (10.100.0.1 <-> 10.100.0.3)
     |
server0.pop11 (10.0.0.14)           <-- API + Postgres + Redis + Sandbox
     | LAN
server1.pop11 (TBD)                 <-- GenOps
     | LAN
maeve.pop11 (10.0.0.81)             <-- Ollama / GPU
```

## Cost Impact

| Before | After |
|--------|-------|
| DO Droplet s-2vcpu-4gb: $24/mo | DO Droplet s-1vcpu-512mb: $4/mo |
| DO Managed Postgres: ~$30/mo | Self-hosted on server0: $0 |
| DO Managed Valkey: ~$20/mo | Self-hosted on server0: $0 |
| **Total: ~$74/mo** | **Total: ~$4/mo** |

## Pre-Migration Checklist

- [ ] WireGuard tunnel between api.mcpworks.io (10.100.0.1) and server0 (10.100.0.3) is up and stable
- [ ] server0 has Docker and Docker Compose installed
- [ ] server0 has sufficient disk space for Postgres data
- [ ] Firewall on server0 allows inbound on port 8000 from 10.100.0.0/24
- [ ] DNS internal record for api.mcpworks.io resolves on WG network
- [ ] JWT key pair generated and placed in server0:/opt/mcpworks/keys/
- [ ] Postgres password file created at server0:/opt/mcpworks/secrets/postgres_password.txt

## Migration Steps

### Phase 1: Prepare server0

```bash
# On server0.pop11
mkdir -p /opt/mcpworks/{keys,secrets}

# Generate postgres password
openssl rand -base64 32 > /opt/mcpworks/secrets/postgres_password.txt
chmod 600 /opt/mcpworks/secrets/postgres_password.txt

# Copy JWT keys from current prod (via WG)
scp root@10.100.0.1:/opt/mcpworks/keys/jwt_*.pem /opt/mcpworks/keys/

# Copy the codebase
git clone <repo-url> /opt/mcpworks/src
# OR rsync from dev machine

# Copy docker-compose and create .env
cp infra/server0/docker-compose.yml /opt/mcpworks/docker-compose.yml
```

### Phase 2: Create .env for server0

```bash
# /opt/mcpworks/.env
# Database now points to local Postgres (container name on Docker network)
DATABASE_URL=postgresql+asyncpg://mcpworks:<password>@postgres:5432/mcpworks
REDIS_URL=redis://redis:6379/0

# Everything else stays the same as current prod .env
# Copy all other vars from api.mcpworks.io:/opt/mcpworks/.env
```

Key changes from current .env:
- `DATABASE_URL` changes from DO Managed (port 25060, SSL) to local container
- `REDIS_URL` changes from `rediss://` (TLS) to `redis://` (local, no TLS needed)

### Phase 3: Migrate Database

```bash
# On api.mcpworks.io — dump from DO Managed Postgres
pg_dump "postgresql://mcpworks:<password>@private-mcpworks-db-do-user-2618613-0.d.db.ondigitalocean.com:25060/mcpworks?sslmode=require" \
    --no-owner --no-privileges -Fc > /tmp/mcpworks-dump.sql

# Transfer to server0
scp /tmp/mcpworks-dump.sql root@10.100.0.3:/tmp/

# On server0 — start only Postgres first
cd /opt/mcpworks
docker compose up -d postgres
sleep 5

# Restore
docker exec -i mcpworks-postgres pg_restore \
    -U mcpworks -d mcpworks --no-owner --no-privileges \
    < /tmp/mcpworks-dump.sql

# Verify
docker exec mcpworks-postgres psql -U mcpworks -c "\dt"
```

### Phase 4: Start Services on server0

```bash
# On server0
cd /opt/mcpworks
docker compose up -d

# Verify API is healthy
curl http://localhost:8000/v1/health
curl http://localhost:8000/v1/health/ready
```

### Phase 5: Switch Edge to Proxy Mode

```bash
# On api.mcpworks.io — test proxy connectivity first
curl http://10.100.0.3:8000/v1/health

# Stop current services
cd /opt/mcpworks
docker compose -f docker-compose.prod.yml down

# Deploy edge config
mkdir -p /opt/mcpworks-edge
cp infra/edge/Caddyfile /opt/mcpworks-edge/
cp infra/edge/docker-compose.yml /opt/mcpworks-edge/

# Start edge proxy
cd /opt/mcpworks-edge
docker compose up -d

# Verify end-to-end
curl https://api.mcpworks.io/v1/health
```

### Phase 6: Downsize DO Droplet

Once stable for 24-48 hours:

```bash
# Snapshot the current droplet first (safety net)
doctl compute droplet-action snapshot <droplet-id> --snapshot-name "pre-downsize-2026-03-30"

# Resize to smallest droplet (Caddy + WireGuard only)
doctl compute droplet-action resize <droplet-id> --size s-1vcpu-512mb --resize-disk=false

# If resize-in-place doesn't work, create new smallest droplet,
# set up WG + Caddy, update DNS A record:
doctl compute domain records update mcpworks.io \
    --record-id <record-id> \
    --record-type A \
    --record-name api \
    --record-data <new-ip>
```

### Phase 7: Decommission DO Managed Services

After 1 week of stable operation:

```bash
# Delete managed Postgres
doctl databases delete <postgres-cluster-id>

# Delete managed Valkey
doctl databases delete <valkey-cluster-id>
```

## CI/CD Updates

GitHub Actions deploy workflow needs updating:

- `DEPLOY_HOST` changes to server0's public-reachable address
  - Option A: SSH through api.mcpworks.io as jump host (`ssh -J root@159.203.30.199 root@10.100.0.3`)
  - Option B: SSH directly to server0 if it has a public IP or port forward
- Deploy path stays `/opt/mcpworks`
- Docker compose file reference changes

## Rollback Plan

If migration fails:
1. On api.mcpworks.io: `cd /opt/mcpworks && docker compose -f docker-compose.prod.yml up -d`
2. DNS still points to api.mcpworks.io, no DNS changes needed
3. DO Managed DBs are still running until Phase 7

## WireGuard Health Monitoring

The WG tunnel is now a critical path. Add monitoring:

```bash
# Cron on api.mcpworks.io — check WG peer every 60s
* * * * * ping -c 1 -W 3 10.100.0.3 > /dev/null 2>&1 || systemctl restart wg-quick@wg0
```

## Outbound NAT

server0 and server1 use api.mcpworks.io as their default gateway for internet-bound traffic via WireGuard. This is already configured — outbound from server0 exits via 159.203.30.199.

Verify:
```bash
# On server0
curl -s ifconfig.me  # Should show 159.203.30.199
```
