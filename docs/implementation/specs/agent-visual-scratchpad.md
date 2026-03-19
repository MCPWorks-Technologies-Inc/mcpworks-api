# Agent Visual Scratchpad - Specification

**Version:** 0.1.0 (Draft)
**Created:** 2026-03-18
**Status:** Draft
**Spec Author:** Simon Carr
**Reviewers:** —

---

## 1. Overview

### 1.1 Purpose

The Agent Visual Scratchpad gives each agent a small web-accessible scratch space where it can publish HTML, JavaScript, and CSS to display data visually. The content is served at a secret, unguessable URL under the agent's `*.agent.mcpworks.io` subdomain.

### 1.2 User Value

Agents process data but have no way to present it visually. When an agent analyzes metrics, generates reports, or monitors systems, the only output path today is text dumped into a channel (Discord, Slack, etc.). Users want dashboards, charts, tables, and interactive views — things that require a browser. The scratchpad lets agents (or the LLMs driving them) write HTML+JS and share a link, turning any agent into a lightweight data visualization tool without requiring separate hosting infrastructure.

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] An agent can publish HTML/JS/CSS content via MCP tool and it becomes immediately accessible at a URL
- [ ] The URL is unguessable (secret token) and shareable
- [ ] Content persists across agent restarts until explicitly cleared or overwritten
- [ ] Storage is bounded at 100 MB per agent with clear enforcement
- [ ] The storage backend is swappable (filesystem now, PV/R2 later) without API changes

### 1.4 Scope

**In Scope:**
- MCP tools: `publish_view`, `get_view_url`, `clear_view`
- REST API endpoints for the same operations
- Static file serving behind a secret token path
- Per-agent storage quota enforcement (100 MB)
- Token generation and rotation
- Auto-posting view URL to agent's configured channel
- `ScratchpadBackend` abstraction with filesystem implementation

**Out of Scope:**
- Server-side rendering or build steps (raw HTML/JS/CSS only)
- WebSocket or SSE from scratchpad pages back to the agent
- Custom domains for scratchpad URLs
- Authentication beyond the secret token (no login wall)
- CDN or caching layer (A1+)
- Collaborative editing or versioning of scratchpad content

---

## 2. User Scenarios

### 2.1 Primary Scenario: Agent Publishes a Dashboard

**Actor:** AI orchestrator running inside an agent
**Goal:** Display monitoring data as a visual dashboard
**Context:** Agent has a scheduled function that collects metrics. After collection, the AI reasons about the data and wants to present it.

**Workflow:**
1. Agent's AI orchestration calls `publish_view` with an `index.html` containing a Chart.js dashboard and inline data
2. Server writes files to the agent's scratchpad storage
3. Server returns the view URL: `https://mcpworkssocial.agent.mcpworks.io/view/a3Bf9x...kQ/`
4. Agent's `auto_channel` is set to `discord`, so the URL is automatically posted
5. User clicks the link, sees the dashboard in their browser
6. Agent updates the dashboard hourly by calling `publish_view` again with fresh data

**Success:** User sees a live-updating visual dashboard via a simple link
**Failure:** If storage quota exceeded, agent receives a clear error with current usage

### 2.2 Secondary Scenario: LLM Requests a View URL During Chat

**Actor:** AI assistant (Claude Code) managing an agent via MCP
**Goal:** Get the current scratchpad URL to share with the user
**Context:** User asks "show me the agent's dashboard"

**Workflow:**
1. AI assistant calls `get_view_url` on the agent
2. Server returns the current view URL (or null if no content published)
3. AI assistant presents the URL to the user
4. User opens it in a browser

**Success:** User gets a clickable link to the agent's visual output
**Failure:** If no content has been published, response clearly says so

### 2.3 Tertiary Scenario: Agent Publishes Multi-File View

**Actor:** AI orchestrator
**Goal:** Publish an HTML page with separate JS and CSS files
**Context:** The visualization is complex enough to warrant separate files

**Workflow:**
1. Agent calls `publish_view` with `files` parameter containing `index.html`, `app.js`, and `style.css`
2. Server writes all files to the scratchpad
3. `index.html` references `./app.js` and `./style.css` using relative paths
4. Browser loads the page and fetches the assets from the same token-protected path

**Success:** Multi-file web app loads correctly with all assets
**Failure:** Files exceeding 100 MB total quota are rejected before any writes

---

## 3. Functional Requirements

### 3.1 Core Capabilities

**REQ-SCRATCH-001: Publish View**
- **Description:** Agents must be able to publish one or more files to their scratchpad via the `publish_view` MCP tool
- **Priority:** Must Have
- **Rationale:** Core capability — without this, the feature doesn't exist
- **Acceptance:** Files are written to storage and immediately accessible via the view URL

**REQ-SCRATCH-002: Secret Token URL**
- **Description:** Each agent's scratchpad is served at `https://{agent-name}.agent.mcpworks.io/view/{token}/` where `token` is a 32-byte URL-safe base64 string generated when the agent is created
- **Priority:** Must Have
- **Rationale:** The token prevents unauthorized access. Anyone with the URL can view, but the URL is unguessable (256 bits of entropy). This is the same security model as Google Docs "anyone with the link" sharing.
- **Acceptance:** Token is cryptographically random, URL-safe, and stable across agent restarts

**REQ-SCRATCH-003: Static File Serving**
- **Description:** The API must serve scratchpad files with correct MIME types for `.html`, `.js`, `.css`, `.json`, `.png`, `.jpg`, `.gif`, `.svg`, `.ico`, `.woff`, `.woff2`
- **Priority:** Must Have
- **Rationale:** Browser needs correct Content-Type to render pages
- **Acceptance:** `index.html` served as `text/html`, `.js` as `application/javascript`, etc. Requests to `/view/{token}/` serve `index.html` by default.

**REQ-SCRATCH-004: Storage Quota**
- **Description:** Each agent's scratchpad is limited to 100 MB total. Publish operations that would exceed the quota are rejected before writing.
- **Priority:** Must Have
- **Rationale:** Prevents unbounded storage consumption. 100 MB is generous for HTML/JS/CSS dashboards.
- **Acceptance:** Quota checked atomically before write. Error includes current usage and limit.

**REQ-SCRATCH-005: Get View URL**
- **Description:** `get_view_url` MCP tool returns the agent's current scratchpad URL, or null if no content exists
- **Priority:** Must Have
- **Rationale:** The LLM needs to retrieve the URL to share it
- **Acceptance:** Returns full HTTPS URL with token. Returns null/empty if scratchpad has no files.

**REQ-SCRATCH-006: Clear View**
- **Description:** `clear_view` MCP tool deletes all files from the agent's scratchpad
- **Priority:** Must Have
- **Rationale:** Agents need to clean up or reset their visual output
- **Acceptance:** All files removed, storage quota freed. View URL returns 404 after clearing.

**REQ-SCRATCH-007: Token Rotation**
- **Description:** `rotate_view_token` MCP tool generates a new token, invalidating the old URL
- **Priority:** Should Have
- **Rationale:** If a URL is leaked, the agent owner should be able to revoke access
- **Acceptance:** New token generated, old URL returns 404, new URL serves content

**REQ-SCRATCH-008: Channel Auto-Post**
- **Description:** When `publish_view` is called and the agent has `auto_channel` configured, the view URL is automatically sent to that channel
- **Priority:** Should Have
- **Rationale:** Agents often want to broadcast their visual output without a separate `send_to_channel` call
- **Acceptance:** URL posted to configured channel after successful publish. Failure to post does not fail the publish.

**REQ-SCRATCH-009: Overwrite Semantics**
- **Description:** `publish_view` replaces all existing files by default. An `append` mode allows adding files without clearing.
- **Priority:** Must Have
- **Rationale:** Most use cases are "replace the whole dashboard." Append mode supports incremental builds.
- **Acceptance:** Default mode deletes existing files before writing new ones. Append mode only adds/overwrites specified files.

### 3.2 Data Requirements

**New columns on Agent model:**

| Column | Type | Notes |
|--------|------|-------|
| `scratchpad_token` | VARCHAR(64) | URL-safe base64, generated on agent creation, nullable (agents created before migration) |
| `scratchpad_size_bytes` | INTEGER | Current total size, default 0 |

**No new tables.** Files are stored in the backend (filesystem/R2), not in the database.

**What data is exposed via MCP:**
- `get_view_url`: Full HTTPS URL string
- `publish_view` response: URL, file count, total size, quota remaining

### 3.3 Integration Requirements

**Upstream Dependencies:**
- Agent model: scratchpad_token column
- SubdomainMiddleware: already routes `*.agent.mcpworks.io` to the API
- MCP create handler: registers new tools

**Downstream Consumers:**
- Caddy: routes `*.agent.mcpworks.io` traffic to API (already configured)
- Channel service: receives view URL for auto-posting
- Agent `describe_agent` tool: includes view URL in agent description

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **Publish latency:** < 100ms for typical dashboard (< 1 MB total files)
- **Serve latency:** < 10ms for cached files, < 50ms for filesystem reads
- **Token efficiency:** `publish_view` response < 100 tokens. `get_view_url` response < 50 tokens.

### 4.2 Security

- **Authentication:** Scratchpad content is public to anyone with the token URL. No additional auth.
- **Authorization:** Only the agent's owner (via authenticated MCP/REST) can publish, clear, or rotate tokens
- **Data Protection:** Scratchpad content is NOT encrypted at rest — it's intentionally public via URL. Treat as user-generated public content.
- **Audit:** Log publish/clear/rotate events with agent_id and file count. Never log file contents.
- **Content Security:** Serve scratchpad pages with restrictive CSP: `default-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; img-src 'self' data: https:;` to allow CDN libraries while limiting exfiltration vectors.
- **Path Traversal:** File paths must be validated and normalized. Reject `..`, absolute paths, and null bytes.

### 4.3 Reliability

- **Availability:** Scratchpad serving is stateless file reads — same availability as the API
- **Error Handling:** Missing files → 404. Invalid token → 404 (not 401, to avoid confirming agent existence). Quota exceeded → structured error before write.
- **Recovery:** If filesystem storage is lost, scratchpads are empty. Agents republish on next cycle. No critical data.
- **Data Integrity:** Publish is atomic — write to temp dir, then rename. Partial writes never served.

### 4.4 Scalability

- **Current Scale:** Filesystem on single droplet, ~100 agents × 100 MB = 10 GB max
- **Future Scale (k3s):** PersistentVolumeClaim per agent or shared PV with directory isolation
- **Future Scale (R2):** Unlimited. Backend swap with zero API changes.
- **Bottleneck:** Filesystem I/O for concurrent serves. Mitigated by in-memory caching of hot files (< 1 MB).

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- Must serve via the existing `*.agent.mcpworks.io` Caddy block — all traffic already routes to the API
- Must NOT require Caddy config changes per agent (on-demand TLS already handles this)
- Storage backend must be swappable via `ScratchpadBackend` interface (same pattern as execution backends)
- File paths within the scratchpad must be flat or shallow (max 3 levels deep) to prevent abuse

### 5.2 Business Constraints

- Timeline: Ship in A0 phase
- Resources: Solo developer
- Infrastructure: filesystem on current droplet, PV on k3s (imminent migration)
- No additional managed services (no S3/R2 in A0)

### 5.3 Assumptions

- Agents publish relatively small content (dashboards, reports) — not media-heavy sites
- Most scratchpads will be < 5 MB (HTML + JS libraries + data)
- Content is ephemeral — agents rebuild it, users don't rely on permanence
- The k3s migration will provide PersistentVolumes for storage continuity
- **Risk if wrong:** If agents try to host large media, 100 MB quota will be hit quickly. Mitigation: quota is per-tier (can be increased for Enterprise/Dedicated in future).

---

## 6. Error Scenarios & Edge Cases

### 6.1 Error Scenario: Quota Exceeded

**Trigger:** `publish_view` with files totaling more than 100 MB (or cumulative in append mode)
**Expected Behavior:** 429 error before any files are written
**User Experience:**
```json
{
  "error": "SCRATCHPAD_QUOTA_EXCEEDED",
  "message": "Scratchpad storage limit exceeded",
  "current_bytes": 98000000,
  "limit_bytes": 104857600,
  "requested_bytes": 15000000
}
```
**Recovery:** Clear existing content or reduce file sizes
**Logging:** Log `scratchpad_quota_exceeded` with agent_id, current size, requested size

### 6.2 Error Scenario: Invalid Token in URL

**Trigger:** User visits `https://agent.agent.mcpworks.io/view/wrong-token/`
**Expected Behavior:** 404 Not Found (not 401/403)
**User Experience:** Generic 404 page
**Rationale:** Returning 401 would confirm the agent exists. 404 reveals nothing.

### 6.3 Error Scenario: Path Traversal Attempt

**Trigger:** `publish_view` with filename `../../etc/passwd` or `/etc/shadow`
**Expected Behavior:** 400 error with validation message
**User Experience:** `{"error": "INVALID_FILENAME", "message": "Filename contains invalid characters or path traversal"}`
**Logging:** Log `scratchpad_path_traversal` as security event

### 6.4 Edge Case: No index.html

**Trigger:** Agent publishes only `data.json` without an `index.html`
**Expected Behavior:** Request to `/view/{token}/` returns 404. Request to `/view/{token}/data.json` serves the file.
**Rationale:** No auto-generated index. The agent is responsible for providing an entry point.

### 6.5 Edge Case: Agent Destroyed

**Trigger:** Agent is destroyed while scratchpad has content
**Expected Behavior:** Scratchpad files are deleted as part of agent cleanup
**Rationale:** No orphaned storage. Cascade delete.

### 6.6 Edge Case: Concurrent Publishes

**Trigger:** Two `publish_view` calls arrive simultaneously
**Expected Behavior:** Last write wins. Atomic rename ensures no partial state is served.
**Rationale:** Agents typically have one orchestration loop. Concurrent publishes indicate a race condition in the caller, and last-write-wins is the safest resolution.

### 6.7 Edge Case: Binary Files

**Trigger:** Agent publishes images (PNG, JPG) or font files (WOFF2)
**Expected Behavior:** Files stored and served with correct MIME type. Binary content passed via base64 in the `publish_view` tool.
**Rationale:** Dashboards often include logos or charts rendered as images.

---

## 7. API Design

### 7.1 MCP Tools (Create Interface)

**`publish_view`**
```json
{
  "name": "publish_view",
  "description": "Publish HTML/JS/CSS content to the agent's visual scratchpad. Creates a web-accessible page at a secret URL.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": {
        "type": "string",
        "description": "Agent name"
      },
      "files": {
        "type": "object",
        "description": "Map of filename to content. Keys are paths (e.g., 'index.html', 'js/app.js'). Values are file content (string for text, base64-prefixed for binary: 'base64:...').",
        "additionalProperties": { "type": "string" }
      },
      "mode": {
        "type": "string",
        "enum": ["replace", "append"],
        "default": "replace",
        "description": "replace: clear existing files first. append: add/overwrite only specified files."
      }
    },
    "required": ["agent_name", "files"]
  }
}
```

**Response:**
```json
{
  "url": "https://mcpworkssocial.agent.mcpworks.io/view/a3Bf9xK2mN7pQ.../",
  "files_written": 3,
  "total_bytes": 45230,
  "quota_remaining_bytes": 104812370
}
```

**`get_view_url`**
```json
{
  "name": "get_view_url",
  "description": "Get the agent's scratchpad view URL.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" }
    },
    "required": ["agent_name"]
  }
}
```

**Response:**
```json
{
  "url": "https://mcpworkssocial.agent.mcpworks.io/view/a3Bf9xK2mN7pQ.../",
  "files": ["index.html", "app.js", "style.css"],
  "total_bytes": 45230
}
```
Or if empty: `{"url": null, "files": [], "total_bytes": 0}`

**`clear_view`**
```json
{
  "name": "clear_view",
  "description": "Delete all files from the agent's scratchpad.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" }
    },
    "required": ["agent_name"]
  }
}
```

**`rotate_view_token`**
```json
{
  "name": "rotate_view_token",
  "description": "Generate a new scratchpad URL token, invalidating the old one.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" }
    },
    "required": ["agent_name"]
  }
}
```

### 7.2 REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/v1/agents/{id}/scratchpad` | Publish files (same as `publish_view`) |
| GET | `/v1/agents/{id}/scratchpad` | Get view URL and file list |
| DELETE | `/v1/agents/{id}/scratchpad` | Clear all files |
| POST | `/v1/agents/{id}/scratchpad/rotate-token` | Rotate token |

### 7.3 View Serving (Public, No Auth)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/view/{token}/` | Serve `index.html` |
| GET | `/view/{token}/{path}` | Serve file at path |

These routes are on the `*.agent.mcpworks.io` host, handled by the existing Caddy wildcard block. The API serves the files directly — no Caddy static file config needed.

---

## 8. Backend Abstraction

### 8.1 ScratchpadBackend Interface

```python
class ScratchpadBackend(ABC):
    @abstractmethod
    async def write_files(
        self, agent_id: UUID, files: dict[str, bytes], mode: str
    ) -> int:
        """Write files. Returns total bytes written."""

    @abstractmethod
    async def read_file(self, agent_id: UUID, path: str) -> bytes | None:
        """Read a single file. Returns None if not found."""

    @abstractmethod
    async def list_files(self, agent_id: UUID) -> list[str]:
        """List all file paths in the scratchpad."""

    @abstractmethod
    async def get_total_size(self, agent_id: UUID) -> int:
        """Get total bytes used."""

    @abstractmethod
    async def clear(self, agent_id: UUID) -> None:
        """Delete all files."""

    @abstractmethod
    async def delete_all(self, agent_id: UUID) -> None:
        """Permanently remove storage (agent destruction)."""
```

### 8.2 FilesystemBackend (A0)

- Base path: `/opt/mcpworks/scratchpad/{agent_id}/`
- Files written with atomic temp-dir + rename
- `get_total_size` walks directory tree
- On k3s: mount a PersistentVolumeClaim at `/opt/mcpworks/scratchpad/`

### 8.3 R2Backend (A1+)

- Bucket: `mcpworks-scratchpad`
- Key prefix: `{agent_id}/`
- Serves via pre-signed URLs or direct API read-through
- Zero filesystem dependency

---

## 9. Token Efficiency Analysis

### 9.1 Tool Definitions

**Estimated tokens for all 4 tool schemas:** ~250 tokens total

### 9.2 Typical Responses

| Operation | Response Size | Notes |
|-----------|---------------|-------|
| `publish_view` | ~60 tokens | URL + counts |
| `get_view_url` | ~50 tokens | URL + file list |
| `clear_view` | ~20 tokens | Confirmation |
| `rotate_view_token` | ~40 tokens | New URL |

### 9.3 Worst Case

**`get_view_url` with many files:** ~150 tokens (50 files listed)
**Mitigation:** File list capped at 50 entries, with `total_count` for overflow

---

## 10. Security Analysis

### 10.1 Threat Model

**Threat:** Token brute-force
**Impact:** Unauthorized access to scratchpad content
**Mitigation:** 32-byte token = 256 bits of entropy. 2^256 attempts required. Rate limiting on `/view/` path.
**Residual Risk:** Negligible

**Threat:** Scratchpad used to host malicious content (phishing, malware)
**Impact:** Reputation, abuse of mcpworks.io domain
**Mitigation:** CSP headers restrict capabilities. Content is user-generated and scoped to their agent. Abuse reports handled via standard process. Token rotation allows takedown.
**Residual Risk:** Medium (inherent in any user-generated content hosting)

**Threat:** XSS from scratchpad page attacking mcpworks.io
**Impact:** Session hijacking on main domain
**Mitigation:** Scratchpad is served on `*.agent.mcpworks.io`, a different subdomain from `api.mcpworks.io`. Cookies are scoped to `api.mcpworks.io` and not accessible from agent subdomains. CSP on scratchpad pages prevents cross-origin requests to the API.
**Residual Risk:** Low

**Threat:** Path traversal writing files outside scratchpad directory
**Impact:** Arbitrary file write on server
**Mitigation:** Strict filename validation: reject `..`, absolute paths, null bytes, control characters. Resolve path and verify it starts with the agent's scratchpad base directory.
**Residual Risk:** Low

**Threat:** Zip bomb / decompression bomb via large base64 content
**Impact:** Disk exhaustion
**Mitigation:** Quota check computed on decoded size before writing. No decompression — files are stored as-is.
**Residual Risk:** Low

### 10.2 PII/Sensitive Data

- Scratchpad content may contain any data the agent processes. This is user-generated content under the user's control.
- Tokens are secrets — never log the full token. Log only the first 8 characters for debugging.

### 10.3 Compliance

- PIPEDA: User controls what they publish. No PII stored by the platform beyond what the user explicitly puts in their scratchpad.
- Content moderation: Out of scope for A0. Standard ToS applies.

---

## 11. Observability Requirements

### 11.1 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `scratchpad_publish_total` | Counter | Total publish operations |
| `scratchpad_publish_bytes` | Histogram | Bytes written per publish |
| `scratchpad_serve_total` | Counter | Total file serve requests |
| `scratchpad_serve_latency_ms` | Histogram | File serve response time |
| `scratchpad_quota_exceeded_total` | Counter | Quota exceeded rejections |
| `scratchpad_storage_bytes` | Gauge (per agent) | Current storage usage |

### 11.2 Logging

**What must be logged:**
- `scratchpad_publish`: agent_id, file_count, total_bytes, mode
- `scratchpad_clear`: agent_id, bytes_freed
- `scratchpad_token_rotated`: agent_id, token_prefix (first 8 chars)
- `scratchpad_serve`: agent_id, path, status_code, response_time_ms
- `scratchpad_quota_exceeded`: agent_id, current_bytes, requested_bytes

**What must NOT be logged:**
- Full scratchpad token
- File contents
- File names (may contain sensitive context in path structure)

### 11.3 Alerting

| Alert | Condition | Severity |
|-------|-----------|----------|
| High scratchpad error rate | > 20 serve errors/minute | Warning |
| Storage approaching limit | > 80% of total disk allocated to scratchpads | Warning |

---

## 12. Testing Requirements

### 12.1 Unit Tests

**Must test:**
- Token generation: correct length, URL-safe characters, uniqueness
- Filename validation: reject traversal, absolute paths, null bytes, control chars
- Quota calculation: correct byte counting, reject over-quota
- MIME type detection: correct types for all supported extensions
- File path normalization: `./foo/../bar` → `bar`
- Base64 binary decoding: correct handling of `base64:` prefix

### 12.2 Integration Tests

**Must test:**
- Full publish → serve cycle: write files, fetch via HTTP, verify content
- Replace mode: publish A, publish B, verify only B files exist
- Append mode: publish A, append B, verify both exist
- Quota enforcement: publish up to limit, verify next publish rejected
- Token rotation: verify old URL 404s, new URL works
- Clear: verify all files removed, quota freed
- Agent destruction: verify scratchpad cleaned up

### 12.3 E2E Tests

**Must test:**
- MCP tool `publish_view` → browser loads `index.html` with working JS/CSS
- Agent with `auto_channel` → view URL appears in channel after publish
- `describe_agent` includes view URL in response

### 12.4 Security Tests

**Must test:**
- Path traversal attempts rejected
- Invalid tokens return 404 (not 401/403)
- CSP headers present on served content
- Token not logged in full anywhere

---

## 13. Migration & Rollout

### 13.1 Database Migration

```sql
ALTER TABLE agents ADD COLUMN scratchpad_token VARCHAR(64);
ALTER TABLE agents ADD COLUMN scratchpad_size_bytes INTEGER NOT NULL DEFAULT 0;
```

Existing agents get `scratchpad_token = NULL`. Token generated on first `publish_view` call or via `rotate_view_token`.

### 13.2 Filesystem Setup

```bash
mkdir -p /opt/mcpworks/scratchpad
chown mcpworks:mcpworks /opt/mcpworks/scratchpad
chmod 750 /opt/mcpworks/scratchpad
```

In Docker: mount as a volume in `docker-compose.prod.yml`.
In k3s: PersistentVolumeClaim mounted at the same path.

### 13.3 Caddy

No changes needed. `*.agent.mcpworks.io` already routes all traffic to the API.

---

## 14. Future Considerations

### 14.1 Phase A1 Enhancements

- **R2 Backend:** Store scratchpad files in Cloudflare R2 for unlimited scale and CDN edge caching
- **Per-Tier Quotas:** Trial: 25 MB, Pro: 100 MB, Enterprise: 500 MB, Dedicated: 2 GB
- **Scratchpad Templates:** Pre-built HTML templates (dashboard, report, chart) that agents can fill with data
- **Live Reload:** WebSocket connection from scratchpad page to API for auto-refresh on publish

### 14.2 Known Limitations

- **No server-side rendering:** Agents must produce complete HTML. No Markdown-to-HTML conversion. Acceptable — LLMs are excellent at generating HTML.
- **No custom domains:** Scratchpad is always on `*.agent.mcpworks.io`. Acceptable for A0.
- **No access analytics:** No tracking of who views the scratchpad. Acceptable — this is a scratch space, not a publishing platform.
- **100 MB fixed quota:** Not tier-differentiated in A0. Acceptable — revisit when real usage data exists.

---

## 15. Spec Completeness Checklist

**Before moving to Plan phase:**

- [x] Clear user value proposition stated
- [x] Success criteria defined and measurable
- [x] All functional requirements enumerated
- [x] All constraints documented
- [x] Error scenarios identified
- [x] Security requirements specified
- [x] Performance requirements quantified
- [x] Token efficiency requirements stated
- [x] Testing requirements defined
- [x] Observability requirements defined
- [x] Reviewed for Constitution compliance
- [ ] Logic checked (internally consistent)
- [ ] Peer reviewed (if team > 1)

---

## 16. Approval

**Status:** Draft

**Approvals:**
- [ ] CTO (Simon Carr)
- [ ] Security Review

**Approved Date:** —
**Next Review:** —

---

## Changelog

**v0.1.0 (2026-03-18):**
- Initial draft
- Backend abstraction designed for filesystem (A0) → R2 (A1) migration
- Intentionally infrastructure-agnostic to survive droplet → k3s migration
