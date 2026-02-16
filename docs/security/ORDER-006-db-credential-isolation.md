# ORDER-006: Database Credential Isolation Verification

**Date:** 2026-02-16
**Status:** VERIFIED

## Isolation Boundary

Sandbox processes (user code) are isolated from database credentials through three layers:

### Layer 1: Environment Variable Isolation
- nsjail config (`python.cfg`) only exposes 4 non-sensitive env vars:
  - `PYTHONPATH=/opt/mcpworks/site-packages:/sandbox`
  - `HOME=/tmp`
  - `LANG=C.UTF-8`
  - `SSL_CERT_FILE=/usr/lib/ssl/cert.pem`
- `DATABASE_URL`, `REDIS_URL`, `STRIPE_SECRET_KEY`, and all other secrets are **not** passed to the sandbox
- The sandbox process runs via nsjail which creates a fresh environment; the parent process's env vars are not inherited

### Layer 2: Network Isolation (iptables)
- `start.sh` configures iptables rules at container startup:
  - **Block** UID 65534 → postgres container IP:5432 (REJECT)
  - **Block** UID 65534 → redis container IP:6379 (REJECT)
  - **Block** UID 65534 → 169.254.169.254 (cloud metadata SSRF)
  - **Block** UID 65534 → 127.0.0.0/8 (localhost SSRF to API:8000)
  - **Rate limit** UID 65534 outbound TCP to 20/sec burst 50
  - **Block** UID 65534 all UDP except DNS (port 53)

### Layer 3: Process Isolation (nsjail)
- Sandbox runs as UID 65534 (nobody) inside its own:
  - PID namespace (can't see host processes)
  - Mount namespace (can't see host filesystem)
  - IPC namespace (can't access host shared memory)
  - UTS namespace (different hostname)
  - User namespace (no capabilities)
- `/proc` mounted with `hidepid=2` (can't see other processes)
- Seccomp default-deny allowlist blocks dangerous syscalls

## What Would Happen If Sandbox Tried to Access DB

1. **Reading env vars:** No DATABASE_URL exists in sandbox environment
2. **Scanning /proc:** `hidepid=2` hides other processes; can only see own PID
3. **Network connection to postgres:** iptables REJECT for UID 65534 → postgres:5432
4. **Network connection to redis:** iptables REJECT for UID 65534 → redis:6379
5. **SSRF to API:** iptables REJECT for UID 65534 → 127.0.0.0/8

## Recommendation

The current isolation is sufficient for A0. No changes needed.
