# POP11 On-Prem Architecture

**Date:** 2026-03-30
**Status:** Live in production
**Replaces:** Single DO droplet architecture (mcpworks-prod)

---

## Overview

MCPWorks production infrastructure runs on-premises on Hyper-V VMs ("POP11") with a single DigitalOcean droplet as the public edge. All application services, databases, and sandboxes run on-prem. The DO droplet is a TLS-terminating reverse proxy only.

## Hosts

| Host | Address | Role | Resources |
|------|---------|------|-----------|
| **api.mcpworks.io** | 159.203.30.199 (public), 10.100.0.1 (WG) | Edge proxy (Caddy only) | DO droplet, minimal |
| **server0.pop11** | 10.0.0.14 (LAN), 10.100.0.3 (WG) | MCPWorks platform (API, Postgres, Redis, sandbox) | Hyper-V VM, 12 vCPU, dynamic RAM |
| **server1.pop11** | TBD (LAN), 10.100.0.4 (WG) | GenOps (genops.dev) | Hyper-V VM (planned) |
| **maeve.pop11** | 10.0.0.81 (LAN only) | Hyper-V host, GPU (RTX 3090), Ollama | NOT on WireGuard |
| **monolith.pop11** | 10.0.0.41 (LAN), 10.100.0.2 (WG) | Dev machine | Simon's workstation |

## Network Architecture

```
[INTERNET]
     │
     ▼
┌─────────────────────┐
│  api.mcpworks.io    │  DO tor1, 159.203.30.199
│  Caddy (TLS only)   │  WG: 10.100.0.1
│  + agent containers │  (agents still here temporarily)
│  + socat proxy      │
└────┬────────────────┘
     │ WireGuard
     ▼
┌──────────────────┐
│  server0.pop11   │  Hyper-V VM on Maeve
│  10.100.0.3 (WG) │
│                  │
│  mcpworks-api    │  FastAPI + nsjail sandbox
│  postgres:16     │  Self-hosted (was DO Managed)
│  redis:7         │  Self-hosted (was DO Managed Valkey)
│  GH Actions      │  Self-hosted runner
│  runner          │
└──────────────────┘
     │ LAN
     ▼
┌──────────────────┐
│  maeve.pop11     │  10.0.0.81
│  Ollama :11434   │  RTX 3090 (24GB VRAM)
│  Hyper-V host    │
└──────────────────┘
```

## Traffic Flow

1. **Inbound:** Internet → api.mcpworks.io (Caddy, TLS) → WireGuard → server0:8000 (API)
2. **Outbound from server0:** server0 → WireGuard → api.mcpworks.io → Internet (NAT)
3. **Agent containers:** Still on api.mcpworks.io, reach API via socat proxy (`mcpworks-api` container) through iptables MASQUERADE to WG peer

## Services on Each Host

### api.mcpworks.io (Edge)

| Container | Purpose | Network |
|-----------|---------|---------|
| `mcpworks-edge-caddy` | TLS termination, reverse proxy to server0/server1 | host |
| `mcpworks-api` (socat) | Bridge for agent containers to reach API on server0 | mcpworks-agents |
| `agent-*` (6 containers) | Agent runtime containers (temporary, will migrate) | mcpworks-agents |

Config: `/opt/mcpworks-edge/` (Caddyfile + docker-compose.yml)

Routing persistence: `/opt/mcpworks-edge/setup-agent-proxy.sh` runs via `mcpworks-agent-proxy.service` on boot to set up iptables rules for agent→API routing.

### server0.pop11

| Container | Purpose | Port |
|-----------|---------|------|
| `mcpworks-api` | FastAPI + nsjail sandbox | 8000 (host) |
| `mcpworks-postgres` | PostgreSQL 16 | 5432 (internal) |
| `mcpworks-redis` | Redis 7 (AOF, 512MB max) | 6379 (internal) |

Config: `/opt/mcpworks/` (docker-compose.yml, .env, keys/, secrets/)
Source: `/opt/mcpworks/src/` (synced by GH Actions runner)
Runner: `/home/user/actions-runner/` (systemd service)

**Docker DNS:** `/etc/docker/daemon.json` overrides DNS to `8.8.8.8` and `1.1.1.1`.
The ISP's IPv4 nameservers (from DHCP) are unreliable — they time out intermittently,
which causes Docker build failures (pip can't resolve pypi.org). Host resolv.conf falls
back to IPv6 DNS, but Docker BuildKit only uses IPv4. This was root-caused on 2026-04-01
after repeated deploy failures.

## Deployment (CI/CD)

**Model:** Pull-based via self-hosted GitHub Actions runner on server0.

```
Push to main
     │
     ├─ CI job (ubuntu-latest, GitHub-hosted)
     │   lint, test, build, security scan
     │
     └─ Deploy job (self-hosted, server0)
         needs: CI passes
         │
         ├─ actions/checkout (runner pulls code)
         ├─ rsync to /opt/mcpworks/src/
         ├─ sudo docker compose build api
         ├─ sudo docker compose up -d api
         └─ health check (local + curl api.mcpworks.io)
```

**No SSH keys in GitHub.** No inbound access from GitHub to servers. Server0 initiates all connections outbound.

Workflows:
- `.github/workflows/ci.yml` — Lint, test, build, security (GitHub-hosted)
- `.github/workflows/deploy.yml` — Production deploy (self-hosted on server0)

### Manual Deploy

```bash
# SSH to server0
ssh user@10.0.0.14   # from LAN
ssh -J user@10.100.0.1 user@10.100.0.3  # from WG

# Deploy
cd /opt/mcpworks
sudo rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' \
    --include='src/***' --include='deploy/***' --include='alembic/***' \
    --include='alembic.ini' --include='scripts/***' --include='Dockerfile' \
    --include='pyproject.toml' --include='README.md' \
    --include='docs/' --include='docs/guide.md' --include='docs/llm-reference.md' \
    --exclude='*' \
    /path/to/mcpworks-api/ /opt/mcpworks/src/
sudo docker compose build api
sudo docker compose up -d api
```

## Database

**Self-hosted PostgreSQL 16** on server0 (was DO Managed).

- Data: Docker volume `mcpworks_postgres-data`
- Auth: password via Docker secret (`/opt/mcpworks/secrets/postgres_password.txt`)
- Connection: `postgresql+asyncpg://mcpworks:<pw>@postgres:5432/mcpworks` (no SSL — local container network)
- Backup: Manual `pg_dump` (TODO: automated backup cron)
- 32 tables as of migration date

## Cost

| Before (DO Cloud) | After (POP11) |
|--------------------|---------------|
| Droplet s-2vcpu-4gb: $24/mo | Droplet (edge only): $4-6/mo |
| DO Managed Postgres: ~$30/mo | Self-hosted: $0 |
| DO Managed Valkey: ~$20/mo | Self-hosted: $0 |
| **Total: ~$74/mo** | **Total: ~$4-6/mo** |

## SSH Access

All access uses the `user` account with passwordless sudo. SSH keys:

| Key | Access |
|-----|--------|
| `user@heist.local` (monolith) | server0, api.mcpworks.io |
| `root@mcpworks-prod` (edge) | server0 (for WG-internal ops) |

No GitHub deploy keys. No external SSH access to any server.

## Remaining Work

- [ ] Migrate agent containers from edge to server0
- [ ] Downsize DO droplet to s-1vcpu-512mb ($4/mo) after agent migration
- [ ] Delete DO Managed Postgres and Valkey after 1-week soak
- [ ] Expand server0 Hyper-V disk (currently 14GB, 48% used)
- [ ] Automated Postgres backup (cron pg_dump to local or S3)
- [ ] Set up server1.pop11 for GenOps
