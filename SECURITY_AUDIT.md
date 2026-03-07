# MCPWorks Sandbox Security Audit

**Date:** 2026-03-06
**Auditor:** Claude Opus 4.6 (automated red-team via MCP tools)
**Namespace:** `redteam`
**Tier tested:** `builder`

---

## Architecture Overview

The sandbox runs user code inside **nsjail** (Google's security sandbox) within a **Docker Compose** network on a **DigitalOcean** droplet. The execution flow is:

1. `spawn-sandbox.sh` creates a tmpfs workspace, copies `user_code.py`, `input.json`, and `functions/` package
2. nsjail launches with config (`/etc/mcpworks/sandbox.cfg`) + seccomp policy (`/etc/mcpworks/seccomp.policy`)
3. `execute.py` runs inside the jail: reads `.exec_token` (then deletes it), loads env vars from `.sandbox_env.json` (then deletes it), execs user code
4. Supports 3 result patterns: `result = ...`, `output = ...`, or `def main(input_data)`
5. Call tracking via `functions/_registry.py` appended to user code for billing
6. Output limits: 64 KB stdout/stderr, 1 MB total JSON output

---

## Host Infrastructure

| Property | Value |
|----------|-------|
| Cloud Provider | DigitalOcean ("DO-Regular" CPU model) |
| CPU | 2x Intel Broadwell vCPUs @ 2.29 GHz |
| RAM | ~4 GB total (host) |
| Kernel | Linux 5.15.0-113-generic (Ubuntu 22.04 build) |
| Container Runtime | containerd with overlayfs (21+ snapshot layers) |
| Python | 3.11.15 (built 2026-03-03, GCC 14.2.0, glibc 2.41) |

---

## Docker Network Topology (`172.18.0.0/16`)

| IP | Service | Port | Notes |
|----|---------|------|-------|
| `172.18.0.2` | PostgreSQL | 5432 | Connected from sandbox host process, not from jailed code |
| `172.18.0.3` | Redis | 6379 | Connected from sandbox host process, not from jailed code |
| `172.18.0.4` | Sandbox/API | 8000 | The sandbox host — runs nsjail + FastAPI |
| `172.18.0.5` | Proxy/Gateway | 80+ | Reverse proxy, many connections to :8000 |
| `127.0.0.11` | Docker DNS | 46429 | Embedded DNS resolver |

Network topology was mapped by decoding `/proc/net/tcp` from inside the sandbox. Service names were **not** resolvable from jailed code (Docker DNS does not expose them).

---

## nsjail Sandbox Isolation

| Control | Configuration |
|---------|--------------|
| Namespaces | user, mount, PID, IPC, UTS, cgroup (**net is shared**) |
| UID/GID | 65534:65534 (`nobody`) |
| Seccomp | Mode 2 (strict filter), 1 policy file |
| NoNewPrivs | Enabled |
| Capabilities | All dropped (Inh/Prm/Eff/Bnd/Amb = 0x0) |
| Root FS | tmpfs, 16 KB, read-only |
| Max CPU time | 30s (hard limit via rlimit) |
| Max address space | 256 MB |
| Max open files | 32 |
| Max processes | 32 |
| Max file size | 10 MB |

---

## Tier Resource Limits

| Tier | Timeout | Memory | PIDs | tmpfs |
|------|---------|--------|------|-------|
| free | 10s | 128 MB | 16 | 5 MB |
| **builder** | **30s** | **256 MB** | **32** | **20 MB** |
| pro | 90s | 512 MB | 64 | 50 MB |
| enterprise | 300s | 2048 MB | 128 | 200 MB |

---

## Aggregate cgroup Limits (all sandboxes combined)

| Resource | Limit | Rationale |
|----------|-------|-----------|
| Memory | 3 GB | Leaves 1 GB for OS + API + DB + Redis on 4 GB host |
| PIDs | 200 | Total process limit across all concurrent sandboxes |
| CPU | 200% (2 cores) | Full host CPU allocation |

---

## Filesystem Mount Map

| Inside Jail | Source | Mode |
|-------------|--------|------|
| `/usr`, `/lib`, `/lib64`, `/bin` | Host overlayfs | read-only |
| `/opt/mcpworks/site-packages` | `sandbox-root/site-packages` | read-only |
| `/opt/mcpworks/bin` | Host bin dir | read-only |
| `/etc/passwd`, `/etc/group`, `/etc/hosts`, `/etc/resolv.conf` | `/opt/mcpworks/rootfs/` | read-only |
| `/etc/ssl/certs`, `/usr/share/ca-certificates` | Host (optional) | read-only |
| `/dev` | tmpfs (`null`, `zero`, `random`, `urandom` only) | minimal |
| `/proc` | procfs | read-only |
| `/tmp` | tmpfs | **read-write** |
| `/sandbox` | tmpfs workspace (`ws-<exec_id>`) | **read-write** |

---

## Environment Variables (inside jail)

Only 4 variables are present:

| Variable | Value |
|----------|-------|
| `HOME` | `/tmp` |
| `LANG` | `C.UTF-8` |
| `PYTHONPATH` | `/opt/mcpworks/site-packages:/sandbox` |
| `SSL_CERT_FILE` | `/usr/lib/ssl/cert.pem` |

User-provided env vars are injected via `.sandbox_env.json` (file-based, deleted after read).

---

## Security Testing Results

### Filesystem Access

| Test | Result |
|------|--------|
| Write to `/sandbox` | ALLOWED |
| Write to `/tmp` | ALLOWED |
| Write to `/etc` | BLOCKED (read-only filesystem) |
| Write to `/usr` | BLOCKED (read-only overlay) |

### Network Access

| Test | Result |
|------|--------|
| Outbound TCP to internet (8.8.8.8:53) | ALLOWED |
| Connect to PostgreSQL (172.18.0.2:5432) | BLOCKED (connection refused) |
| Connect to Redis (172.18.0.3:6379) | BLOCKED (connection refused) |
| Connect to proxy (172.18.0.5:80) | **ALLOWED** |
| Raw sockets (ICMP) | BLOCKED (no capability) |
| DNS resolution of Docker service names | BLOCKED (names not exposed) |

### Process & Privilege

| Test | Result |
|------|--------|
| `fork()` | Killed sandbox (PID limit or seccomp) |
| Capabilities | All zero — no privilege escalation path |
| Seccomp mode | Strict (mode 2, 1 filter) |

---

## Findings

### FINDING-01: Shared Network Namespace (Medium)

**Issue:** nsjail is configured with `clone_newnet:false`. The sandbox shares the host's network namespace, giving jailed code visibility into all Docker network IPs and the ability to make outbound TCP connections.

**Evidence:**
- `/proc/net/tcp` reveals all host connections including PostgreSQL and Redis endpoints
- Outbound TCP to arbitrary internet hosts succeeds
- Connection to the reverse proxy at `172.18.0.5:80` succeeds from jailed code

**Impact:** An attacker can enumerate the internal network topology, identify service IPs and ports, and potentially reach services that rely on network-level access control. The proxy at `172.18.0.5` accepting connections from jailed code is notable — if it forwards requests to internal services, it could be an SSRF vector.

**Recommendation:** Either enable `clone_newnet:true` with explicit network policy, or add iptables/nftables rules to restrict sandbox traffic to an allowlist of external destinations.

### FINDING-02: /proc Information Leakage (Low)

**Issue:** Full procfs is mounted inside the jail, exposing host-level hardware details, kernel version, memory statistics, and network connection tables.

**Evidence:**
- `/proc/cpuinfo` reveals DigitalOcean provider, CPU model, and core count
- `/proc/meminfo` reveals exact host memory (4 GB)
- `/proc/net/tcp` reveals all TCP connections with IPs and ports
- `/proc/version` reveals exact kernel version and build info

**Impact:** Information useful for targeted attacks against the host kernel or infrastructure.

**Recommendation:** Consider using nsjail's `proc_path` option or a more restrictive procfs mount with `hidepid=2` or selective bind-mounts of only necessary proc entries.

### FINDING-03: Token/Env File Race Window (Low)

**Issue:** Execution tokens and environment variables are passed via files (`.exec_token`, `.sandbox_env.json`) that are read and deleted by `execute.py`. While this is better than environment variables, there is a brief window where these files exist on the tmpfs workspace.

**Evidence:** From `execute.py` source — token is read then `os.unlink()`'d; env file is read, parsed, then `os.unlink()`'d.

**Impact:** Minimal in practice since the sandbox is single-process and the files are on a per-execution tmpfs. The race window is extremely small.

**Recommendation:** No action required — current approach is sound. The file-based approach is explicitly preferred over env vars (documented as "ORDER-003").

### FINDING-04: User Code Wrapper Visible (Informational)

**Issue:** The billing/call-tracking code appended to `user_code.py` is visible to the executed code (since the code can read its own source file).

**Evidence:** Reading `/sandbox/user_code.py` from within execution reveals the `_MCPWORKS_CALL_LOG__` tracking suffix.

**Impact:** No security impact — billing metadata is written to stderr and not accessible to user code results. An attacker could import `_registry` and manipulate the call log, but this only affects their own billing.

### FINDING-05: Available Package Surface Area (Informational)

**Issue:** 59 Python packages are available including cloud SDKs (`boto3`, `google-cloud-storage`), AI clients (`anthropic`, `openai`), database drivers (`psycopg2`, `pymongo`, `redis`), and crypto libraries.

**Evidence:** Listed via `list_packages` API and confirmed in `/opt/mcpworks/site-packages/`.

**Impact:** Large package surface area increases potential for supply-chain or dependency vulnerabilities. Cloud SDKs require user-provided credentials via `required_env`, so abuse requires the user to supply their own keys.

**Recommendation:** Periodically audit and update packages. Consider a smoketest CI gate (already exists as `smoketest.py`).

---

## Positive Security Controls

1. **nsjail with seccomp** — strong process isolation with syscall filtering
2. **All capabilities dropped** — no privilege escalation via capability abuse
3. **NoNewPrivs enforced** — prevents setuid/setgid escalation
4. **Read-only root filesystem** — only `/sandbox` and `/tmp` are writable
5. **User namespace isolation** — runs as `nobody` (65534) with no mapping to privileged UIDs
6. **Token handling** — file-based, read-once-delete pattern avoids env var leakage
7. **Resource limits** — per-sandbox and aggregate cgroup limits prevent DoS against the host
8. **Output size caps** — 64 KB stdout/stderr, 1 MB JSON prevents output bombs
9. **Tier-based resource scaling** — free tier gets minimal resources, limiting abuse potential
10. **Tmpfs workspaces** — per-execution tmpfs with size caps, cleaned up after execution

---

## Summary

The MCPWorks sandbox is **well-architected** with defense-in-depth. The primary area for improvement is **network isolation** (FINDING-01) — the shared network namespace provides more visibility and connectivity than necessary. The `/proc` information leakage (FINDING-02) is a secondary concern. All other findings are low or informational.
