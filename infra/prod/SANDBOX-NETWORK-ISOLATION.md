# Sandbox Network Isolation

## Overview

The MCPWorks sandbox runs user code inside **nsjail** within the API container.
nsjail is configured with `clone_newnet: false` (shared network namespace) so
that user functions can make outbound HTTP requests to external APIs.

This means sandbox code has raw TCP access to the container's network. Without
iptables rules, sandboxed code could reach PostgreSQL, Redis, the API itself,
and the Caddy reverse proxy — all on the Docker bridge network.

## Threat Model

| Target | IP (typical) | Risk |
|--------|-------------|------|
| PostgreSQL | 172.18.0.2:5432 | Direct DB access |
| Redis | 172.18.0.3:6379 | Session/rate-limit tampering |
| API (self) | 172.18.0.4:8000 | SSRF to internal endpoints |
| Caddy proxy | 172.18.0.5:80 | SSRF via reverse proxy to API |
| Cloud metadata | 169.254.169.254 | Credential theft (DO/AWS/GCP) |
| Docker DNS | 127.0.0.11 | Service name resolution |

## Defense Layers

Two independent iptables rule sets block sandbox UID 65534:

### Layer 1: Container startup (`scripts/start.sh`)

Runs every time the API container starts. Resolves IPs dynamically via Docker DNS.

| Rule | Target | Action |
|------|--------|--------|
| Postgres IP:5432 | Resolved via `getent hosts postgres` | REJECT |
| Redis IP:6379 | Resolved via `getent hosts redis` | REJECT |
| 169.254.169.254 | Cloud metadata | REJECT |
| 127.0.0.0/8 | Localhost (API on :8000) | REJECT |
| Docker subnet | Auto-detected from `ip route` or fallback 172.16.0.0/12 + 10.0.0.0/8 | REJECT |
| UDP (non-DNS) | All UDP except port 53 | REJECT |
| TCP SYN | Rate limited 20/sec burst 50 | REJECT on exceed |

### Layer 2: Host setup (`deploy/server-setup.sh`)

Runs once during server provisioning. Persisted via `iptables-save`.

| Rule | Target | Action |
|------|--------|--------|
| Port 5432 | Any destination | DROP |
| Port 6379 | Any destination | DROP |
| 172.16.0.0/12 | Docker bridge range | DROP |
| 10.0.0.0/8 | Private range | DROP |
| 169.254.169.254 | Cloud metadata | DROP |

### Why Two Layers?

- **Container rules** are authoritative — they run on every restart and resolve
  actual service IPs. If Docker reassigns IPs, the rules update automatically.
- **Host rules** are defense-in-depth — they persist across container restarts
  and catch edge cases where the container rules might not apply (e.g., during
  startup before `start.sh` runs).

## What IS Allowed

- Outbound TCP to the public internet (any IP not in blocked ranges)
- DNS resolution (UDP port 53)
- TLS connections to external APIs (httpx, requests, etc.)

## Verification

From inside a sandbox execution, these should all fail:

```python
import socket

# Should all raise ConnectionRefusedError or timeout
socket.create_connection(("172.18.0.2", 5432), timeout=2)   # postgres
socket.create_connection(("172.18.0.3", 6379), timeout=2)   # redis
socket.create_connection(("172.18.0.4", 8000), timeout=2)   # API (self)
socket.create_connection(("172.18.0.5", 80), timeout=2)     # Caddy
socket.create_connection(("169.254.169.254", 80), timeout=2) # metadata
```

And this should succeed:

```python
import httpx
httpx.get("https://httpbin.org/ip")  # external internet access
```

## Host Information Obfuscation

In addition to network isolation, the sandbox hides host details that are
irrelevant to code execution (SECURITY_AUDIT.md FINDING-02).

| Path | Real content | What sandbox sees |
|------|-------------|-------------------|
| `/proc/net/*` | Full TCP/UDP connection table, routing | **Not overlaid** (nsjail limitation, see below) |
| `/proc/cpuinfo` | DigitalOcean, CPU model, core count | "Virtual CPU", 1 core |
| `/proc/meminfo` | Host RAM (4 GB) | Tier memory limit only (e.g., 256 MB) |
| `/proc/version` | Kernel version + build info | `Linux version 0.0.0 (sandbox)` |

**Implementation:**
- `/proc/net` — **cannot be overlaid**. nsjail's `move_mount()` rejects both
  tmpfs and bind-mount overlays on procfs subdirectories. This is a known
  limitation of the pinned nsjail commit (`d20ea0a58ab5`). The information is
  read-only and network-level threats are mitigated by iptables UID-based rules.
  Full network namespace isolation (`clone_newnet: true` + veth) would eliminate
  this entirely (see TODO).
- `/proc/cpuinfo`, `/proc/version` — static fake files generated in workspace,
  bind-mounted read-only via `--bindmount_ro` (`spawn-sandbox.sh`)
- `/proc/meminfo` — tier-aware fake (uses `$MEMORY` from tier config),
  bind-mounted read-only via `--bindmount_ro` (`spawn-sandbox.sh`)

**Preserved:** `/proc/self/*` (Python runtime needs it), `/proc/filesystems`,
`/proc/stat` (read-only, low information value).

## Reproducing the Setup

1. Run `deploy/server-setup.sh` on a fresh Ubuntu 22.04 droplet
2. Deploy via `docker compose -f docker-compose.prod.yml up -d`
3. `scripts/start.sh` executes automatically inside the API container
4. Verify with a test function that attempts internal connections

## Related Files

| File | Purpose |
|------|---------|
| `scripts/start.sh` | Container-level iptables + sandbox init |
| `deploy/server-setup.sh` | Host-level iptables + server provisioning |
| `docker-compose.prod.yml` | Network topology (mcpworks-net bridge) |
| `SECURITY_AUDIT.md` | Full red-team audit results |
| `/etc/mcpworks/sandbox.cfg` | nsjail configuration (on prod server) |
| `/etc/mcpworks/seccomp.policy` | Seccomp syscall filter (on prod server) |
