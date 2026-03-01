# MCPWorks API — Technical Orders

**Issued:** 2026-02-16
**Authority:** Board Meeting 2026-02-16 (see `../mcpworks-internals/docs/governance/board-meeting-2026-02-16.md`)
**Objective:** Ship Code Sandbox to first users. Security first, then onboarding, then iterate.
**Review Date:** March 16, 2026

---

## Standing Orders

These apply to ALL work in this repository until the review date:

1. **No new backends.** Activepieces, nanobot.ai, and GitHub Repo are deferred to A1. Code Sandbox only.
2. **No strategy rewrites.** Strategy documents are frozen for 60 days (until April 16, 2026).
3. **Ship over polish.** If it works for 5 users, ship it. Perfectionism is the enemy.
4. **User feedback drives priorities.** After pilot onboarding, adjust based on what real users say.

---

## Phase 1: Security Hardening (BLOCKING — before any external user)

**Target: Complete by Feb 23, 2026**

These issues were identified in the sandbox security review (2026-01-17) and remain unresolved. No external user should execute code until these are fixed.

### ORDER-001: Switch seccomp to default-deny allowlist

**Priority:** CRITICAL
**Effort:** 2-3 days
**Location:** Sandbox/nsjail configuration

The current seccomp policy uses a blocklist — new kernel syscalls are auto-allowed. This is the most common sandbox escape vector.

**Requirements:**
- Default-deny seccomp policy
- Explicit allowlist for Python stdlib needs (read, write, open, close, mmap, brk, futex, etc.)
- Block: `clone`, `unshare`, `setns` (namespace escape), `open_by_handle_at` (container escape CVE-2015-1335), `personality` (disables ASLR), IPC syscalls (`shmget`, `shmat`, `msgget`, `semget`)
- Test: All 60+ pre-installed packages still work under the allowlist
- Test: Malicious syscall attempts are blocked and logged

### ORDER-002: Implement aggregate cgroup limits

**Priority:** CRITICAL
**Effort:** 1 day
**Location:** Sandbox/nsjail configuration, host system

10 concurrent sandbox executions can OOM the 4GB host. No aggregate limits exist.

**Requirements:**
- Parent cgroup `/sys/fs/cgroup/mcpworks/` with:
  - `memory.max`: 3GB (leave 1GB for OS + API + DB + Redis)
  - `pids.max`: 200 total
  - `cpu.max`: 200% of one CPU (2 cores)
- All nsjail sandboxes run under this parent cgroup
- Test: Concurrent execution stress test (10 sandboxes simultaneously)

### ORDER-003: Fix token injection (env var → file descriptor)

**Priority:** HIGH
**Effort:** 1 day
**Location:** `src/mcpworks_api/sandbox/`

Execution tokens are passed via environment variable, visible in `/proc/self/environ`.

**Requirements:**
- Pass token via stdin (read once, close) OR unix socket with `SO_PEERCRED`
- Short-lived (30s), single-use execution tokens
- Token not visible in any `/proc` path inside sandbox

### ORDER-004: Add required mounts to nsjail config

**Priority:** HIGH
**Effort:** 0.5 days
**Location:** Sandbox/nsjail configuration

Python stdlib breaks without `/proc` and `/dev` nodes.

**Requirements:**
- Mount `/proc` with `hidepid=invisible` (read-only)
- Mount static `/dev` with: `null`, `zero`, `random`, `urandom`, `fd` symlinks (read-only)
- Test: Python `ssl`, `hashlib`, `random` modules work inside sandbox

### ORDER-005: Audit sandbox packages

**Priority:** HIGH
**Effort:** 0.5 days
**Location:** Sandbox environment / Dockerfile

60+ packages without CVE scanning.

**Requirements:**
- Run `pip audit` on the sandbox Python environment
- Remove any packages with known critical CVEs that don't have patches
- Remove unnecessary packages (reduce attack surface)
- Document the final approved package list
- Set up weekly `pip audit` as part of CI

### ORDER-006: Verify database credential isolation

**Priority:** HIGH
**Effort:** 0.5 days
**Location:** `src/mcpworks_api/sandbox/`, Docker Compose configuration

The spec warns: "Database credentials should NEVER be on the execution host."

**Requirements:**
- Verify: sandbox processes cannot access DATABASE_URL or any DB credentials
- Verify: sandbox processes cannot reach PostgreSQL port (5432) even if they escape nsjail
- Document the isolation boundary in a brief security note

### ORDER-020: Stop logging PII in execution records

**Priority:** CRITICAL
**Effort:** 0.5 days
**Location:** `src/mcpworks_api/models/execution.py`, `src/mcpworks_api/services/`
**Spec:** `../mcpworks-internals/docs/implementation/logging-specification.md`

The Execution model stores `input_data` and `result_data` as JSONB by default. These fields will contain user-supplied function arguments -- potentially PII, financial data, credentials, health data. This is over-logging and creates liability before pilot users.

**Requirements:**
- Stop writing `input_data` and `result_data` by default in `ExecutionService.start_execution()`
- Pass `input_data=None` and `result_data=None` to the model unless a per-function debug flag is set
- Keep the columns nullable for future opt-in debug logging (A1)
- Alembic migration not needed if columns are already nullable; verify

### ORDER-021: Add structured JSON logging

**Priority:** HIGH
**Effort:** 0.5 days
**Location:** `src/mcpworks_api/`, dependencies

Bare `logging.getLogger(__name__)` calls produce unstructured logs. Structured JSON enables log forwarding and operational debugging.

**Requirements:**
- Add `structlog` or `python-json-logger` to dependencies
- Configure structured JSON output for all application logging
- Per-request log entry: timestamp, endpoint (create/run), namespace, function, backend, HTTP status, duration_ms, account_id, request/response size bytes
- Never log: request bodies, response bodies, IP addresses, API keys, user content

### ORDER-022: Implement security events table

**Priority:** HIGH
**Effort:** 1 day
**Location:** `src/mcpworks_api/models/`, `src/mcpworks_api/middleware/`

The A0 plan schema includes `security_events` but it is not yet implemented. Needed for auth failure tracking, quota exceeded visibility, and sandbox violation logging.

**Requirements:**
- Create `security_events` table: id, timestamp, event_type, actor_id, actor_ip_hash (SHA-256, NOT raw IP), endpoint_type, namespace, details (JSONB, no PII), severity
- Alembic migration
- Wire into: auth middleware (log failures), billing middleware (log quota exceeded), sandbox executor (log nsjail violations)
- `GET /v1/audit/logs` endpoint (read-only, account-scoped) -- can be basic for A0

### ORDER-023: Truncate error messages and PII scrub

**Priority:** HIGH
**Effort:** 0.5 days
**Location:** `src/mcpworks_api/models/execution.py`, `src/mcpworks_api/services/`

Error messages from backend execution may contain user data (embedded in tracebacks, exception strings).

**Requirements:**
- Truncate `error_message` field to 255 characters before persisting
- Apply basic PII scrub: strip email patterns (`\S+@\S+`), phone patterns, and anything resembling API keys (`sk-`, `mcpw_`, bearer tokens)
- Log only `error_code` (machine-readable) in structured logs, not `error_message`

---

## Phase 2: Legal Infrastructure (BLOCKING — before any paying customer)

**Target: Complete by Feb 23, 2026 (parallel with Phase 1)**

### ORDER-007: Add legal document endpoints

**Priority:** CRITICAL
**Effort:** 0.5 days
**Location:** `src/mcpworks_api/api/`, static files, `../www.mcpworks.io/`
**Status:** LEGAL DOCS DRAFTED — Ready for implementation

The Privacy Policy, Terms of Service, and Acceptable Use Policy have been drafted and approved in `mcpworks-internals`:
- `../mcpworks-internals/docs/legal/privacy-policy.md` (v1.0.0, 402 lines)
- `../mcpworks-internals/docs/legal/terms-of-service.md` (v1.0.0, 430 lines)
- `../mcpworks-internals/docs/legal/acceptable-use-policy.md` (v1.0.0, 234 lines)

**Authority:** Board Meeting 2026-02-16 Legal Docs Session (`../mcpworks-internals/docs/governance/board-meeting-2026-02-16-legal-docs.md`)

**Requirements:**

**Step 1: Publish on www.mcpworks.io (Eleventy static site)**
- Create `content/privacy.md` with layout `layout.njk`, content from privacy-policy.md
- Create `content/terms.md` with layout `layout.njk`, content from terms-of-service.md
- Create `content/aup.md` with layout `layout.njk`, content from acceptable-use-policy.md
- Each page accessible at:
  - `https://www.mcpworks.io/privacy`
  - `https://www.mcpworks.io/terms`
  - `https://www.mcpworks.io/aup`
- Add footer links to all three documents on every page
- Push to main → auto-deploys to DigitalOcean (~2 min)

**Step 2: API endpoints (redirect to www)**
- `GET /legal/privacy` → 302 redirect to `https://www.mcpworks.io/privacy`
- `GET /legal/terms` → 302 redirect to `https://www.mcpworks.io/terms`
- `GET /legal/aup` → 302 redirect to `https://www.mcpworks.io/aup`
- Alternatively: serve rendered HTML directly from the API if preferred for API-only users

**Step 3: Registration response links**
- Include `legal.privacy_policy`, `legal.terms_of_service`, `legal.acceptable_use_policy` URLs in:
  - `POST /v1/auth/register` response body
  - `POST /v1/auth/api-keys` response body
  - Any onboarding-related endpoint responses

**Email aliases to configure (Google Workspace):**
- `privacy@mcpworks.io` → simon.carr@mcpworks.io
- `legal@mcpworks.io` → simon.carr@mcpworks.io
- `abuse@mcpworks.io` → simon.carr@mcpworks.io
- `security@mcpworks.io` → simon.carr@mcpworks.io
- `support@mcpworks.io` → simon.carr@mcpworks.io

### ORDER-008: Add ToS consent to registration

**Priority:** CRITICAL
**Effort:** 0.5 days
**Location:** `src/mcpworks_api/api/` (auth routes), `src/mcpworks_api/models/`
**Status:** LEGAL DOCS DRAFTED — Ready for implementation
**Depends on:** ORDER-007 (legal docs must be published first)

**Requirements:**
- Add `tos_accepted_at: datetime | None` field to User model
- Add `tos_version: str | None` field to User model (track which version was accepted, e.g. "1.0.0")
- Registration endpoint requires `accept_tos: bool = True` parameter
- Reject registration if `accept_tos` is not True
- Store the ToS version accepted at registration time
- Alembic migration for new fields
- Registration response must include links to all 3 legal documents (see ORDER-007 Step 3)
- Single checkbox consent covers ToS + Privacy Policy + AUP (per board decision)
- Existing users: plan for retroactive consent notification (email)

**Web registration flow (ORDER-009):**
- Single checkbox: "I agree to the [Terms of Service](link) and [Privacy Policy](link)"
- AUP acceptance is implicit via ToS Section 1 (ToS references AUP)
- No forced-scroll, no separate checkboxes per document

---

## Phase 3: User Onboarding (Target: Feb 24 - Mar 2)

### ORDER-009: Web registration page

**Priority:** P0
**Effort:** 3-5 days
**Location:** New — `src/mcpworks_api/static/` or separate frontend

Users currently must call `POST /v1/auth/register` via API. This filters out 80%+ of potential users.

**Requirements:**
- `/register` — email/password signup form
- `/login` — login form
- After login: show namespace creation + `.mcp.json` config snippet
- Minimal — can be server-rendered HTML from FastAPI (Jinja2 templates) or a simple static SPA
- Must call existing auth API endpoints
- Mobile-responsive

### ORDER-010: .mcp.json config generator

**Priority:** P0
**Effort:** 0.5 days
**Location:** Post-login onboarding flow

**Requirements:**
- After user creates namespace, display copy-paste `.mcp.json` config:
  ```json
  {
    "mcpServers": {
      "{namespace}-create": {
        "type": "http",
        "url": "https://{namespace}.create.mcpworks.io/mcp",
        "headers": { "Authorization": "Bearer {api_key}" }
      },
      "{namespace}-run": {
        "type": "http",
        "url": "https://{namespace}.run.mcpworks.io/mcp",
        "headers": { "Authorization": "Bearer {api_key}" }
      }
    }
  }
  ```
- One-click copy button
- Brief instructions: "Paste this into your project's `.mcp.json` file"

### ORDER-011: Function templates (hello-world + 4 more)

**Priority:** P0
**Effort:** 3-5 days
**Location:** `src/mcpworks_api/` (new template system or seeded functions)

Nobody knows what to build first. Templates demonstrate value in 60 seconds.

**Requirements:**
- `hello-world` — Simple input/output function (proves the system works)
- `csv-analyzer` — Upload CSV data, get summary statistics
- `api-connector` — Call an external API, transform the response
- `slack-notifier` — Send a formatted message to Slack webhook
- `scheduled-report` — Generate and format a report
- Each template: pre-filled code + description + input_schema + output_schema
- One-click "clone this function" in onboarding flow or via MCP `make_function` with template parameter

### ORDER-012: Getting-started documentation

**Priority:** P0
**Effort:** 1-2 days
**Location:** `docs/` or served via API/website

**Requirements:**
- Single page: "From zero to first function in 5 minutes"
- Steps: Register → Create namespace → Copy `.mcp.json` → Ask AI to create function → Execute
- Include the hello-world template walkthrough
- Can be markdown served at `GET /docs/quickstart` or on www.mcpworks.io

---

## Phase 4: Observability & Operations (Target: Mar 3-9)

### ORDER-013: Error tracking (Sentry)

**Priority:** P1
**Effort:** 0.5 days
**Location:** `src/mcpworks_api/main.py`, dependencies

**Requirements:**
- Sentry free tier integration
- Capture unhandled exceptions with request context
- Capture sandbox execution failures
- Alert on error rate spike

### ORDER-014: Automated database backups

**Priority:** P1
**Effort:** 0.5 days
**Location:** `deploy/`, cron job on production

**Requirements:**
- Daily `pg_dump` to local file
- Retain 7 days of backups
- Test restore procedure once
- Document backup/restore in deploy docs

### ORDER-015: Health check hardening

**Priority:** P1
**Effort:** 0.5 days
**Location:** `src/mcpworks_api/api/` (health routes), Caddyfile

**Requirements:**
- `/v1/health/ready` verifies: DB connection, Redis connection, sandbox binary exists
- Caddy configured to use `/v1/health/ready` for upstream health checks
- If health check fails, Caddy returns 503 (not route to dead backend)

### ORDER-016: Minimal usage dashboard

**Priority:** P1
**Effort:** 2-3 days
**Location:** `src/mcpworks_api/static/` or frontend

**Requirements:**
- `/dashboard` — requires login
- Show: list of namespaces, services, functions
- Show: execution count, quota remaining, billing period
- Show: API keys (masked) with ability to create new / revoke
- Link to Stripe customer portal for billing self-service

---

## Phase 5: Measurement & Content (Target: Mar 3-9)

### ORDER-017: Token savings measurement

**Priority:** P1
**Effort:** 1-2 days
**Location:** Instrumentation in MCP transport + sandbox

**Requirements:**
- Measure actual token usage for 5-10 real scenarios:
  - Traditional approach: load full MCP tool definitions + execute
  - MCPWorks approach: Code Sandbox function call
- Document results with real numbers
- Produce a brief writeup: "We measured X tokens traditional vs Y tokens MCPWorks = Z% savings"
- This becomes the core marketing proof point

### ORDER-018: Demo recording setup

**Priority:** P1
**Effort:** 0.5 days
**Location:** N/A (screen recording)

**Requirements:**
- Record 90-second demo showing:
  1. Adding MCPWorks to `.mcp.json` (10s)
  2. Asking Claude Code to create a function (20s)
  3. Function being created via MCP tools (20s)
  4. Executing function, getting results (20s)
  5. Real output from sandbox (20s)
- Export as MP4 + GIF
- This is the single most important marketing asset

---

## Phase 6: Financial Fixes (Target: Mar 10-16)

### ORDER-019: Cap Founder Enterprise executions

**Priority:** P1
**Effort:** 0.5 days
**Location:** `src/mcpworks_api/` (billing/usage logic)

The "unlimited" Founder Enterprise tier at $129/month is a financial liability. One heavy user could cost $500+/month in compute.

**Requirements:**
- Change Founder Enterprise from "unlimited" to 100,000 executions/month
- Update Stripe product metadata if needed
- Update any API responses that mention "unlimited"
- Standard Enterprise ($299+) can remain "Custom" limits (negotiated per customer)

---

## Completion Checklist

By March 16, 2026 (30-day review), the following should be true:

- [ ] Seccomp allowlist implemented and tested (ORDER-001)
- [ ] Aggregate cgroup limits in place (ORDER-002)
- [ ] Token injection fixed (ORDER-003)
- [ ] Sandbox mounts corrected (ORDER-004)
- [ ] Package audit complete (ORDER-005)
- [ ] DB credential isolation verified (ORDER-006)
- [ ] Execution model stops logging PII by default (ORDER-020)
- [ ] Structured JSON logging in place (ORDER-021)
- [ ] Security events table capturing auth failures and quota hits (ORDER-022)
- [ ] Error messages truncated and PII-scrubbed (ORDER-023)
- [ ] Legal documents served and consent required (ORDER-007, ORDER-008)
- [ ] Web registration live (ORDER-009)
- [ ] .mcp.json config generator working (ORDER-010)
- [ ] At least hello-world template available (ORDER-011)
- [ ] Getting-started doc published (ORDER-012)
- [ ] Sentry capturing errors (ORDER-013)
- [ ] Database backups running (ORDER-014)
- [ ] 5+ pilot users onboarded
- [ ] Token savings measured and documented (ORDER-017)
- [ ] Demo video recorded (ORDER-018)
- [ ] Founder Enterprise capped (ORDER-019)

---

## Out of Scope (Deferred to A1)

Do NOT work on any of these until the review date and board approval:

- Activepieces backend integration
- nanobot.ai backend
- GitHub Repo backend
- SSE streaming for long operations
- Advanced analytics dashboard
- SOC 2 compliance features
- Multi-account support
- IP allowlisting enforcement
- Webhook event delivery system
- OAuth 2.1 for dashboard
- TypeScript/Node.js sandbox support
- Marketplace or third-party provider features
- Human-In-The-Loop (HITL) for function execution (see `../mcpworks-internals/docs/implementation/hitl-function-execution.md`)
- Opt-in debug logging (input/output capture per function)

---

**Reference:** `../mcpworks-internals/docs/governance/board-meeting-2026-02-16.md`
