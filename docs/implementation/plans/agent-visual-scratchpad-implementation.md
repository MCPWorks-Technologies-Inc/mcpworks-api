# Agent Visual Scratchpad — Implementation Plan

**Version:** 2.0.0
**Last Updated:** 2026-03-18
**Status:** Approved — Board reviewed, all conditions accepted
**Source Specification:** `../specs/agent-visual-scratchpad.md`

---

## Overview

This plan implements the Agent Visual Scratchpad feature: a per-agent web scratch space where agents (or LLMs managing them) publish HTML/JS/CSS content served at a secret, unguessable URL. The implementation is designed to survive the imminent k3s migration by abstracting storage behind a backend interface.

**Estimated effort:** 6 tasks across 4 phases (reduced from 8 after board review)
**Dependencies:** None — builds on existing agent model, subdomain routing, and MCP tool infrastructure

### Board Review Decisions (2026-03-18)

| Decision | Source |
|----------|--------|
| Defer `rotate_view_token` to A1 fast-follow | CEO + CPO |
| Defer REST API endpoints (Task 3.2) to A1 | CFO |
| Defer channel auto-post (Task 4.3) to A1 | CEO |
| Add `Path.resolve()` + prefix re-check for symlink protection | CTO |
| Add per-IP rate limiting on `/view/` route (60 req/min) | CTO |
| Add `X-Robots-Tag: noindex, nofollow` to scratchpad responses | CPO |
| Add `X-Scratchpad-Updated` header with publish timestamp | CPO |
| Document single-writer constraint (ReadWriteOnce PVC) | CTO |
| Align scratchpad quotas with PRICING.md tiers | CFO |

### Scratchpad Quotas (aligned with PRICING.md)

| Tier | Scratchpad Access | Quota/Agent |
|------|-------------------|-------------|
| Trial | No | 0 (feature disabled) |
| Pro | Yes | 100 MB |
| Enterprise | Yes | 1 GB |
| Dedicated | Yes | Unlimited (capped at 10 GB) |

---

## Phase 1: Storage Backend & Data Model

### Task 1.1: ScratchpadBackend Interface + Filesystem Implementation

**Files to create:**
- `src/mcpworks_api/scratchpad/__init__.py`
- `src/mcpworks_api/scratchpad/base.py` — ABC
- `src/mcpworks_api/scratchpad/filesystem.py` — A0 implementation

**ScratchpadBackend ABC (`base.py`):**

```python
from abc import ABC, abstractmethod
from uuid import UUID

class ScratchpadBackend(ABC):
    @abstractmethod
    async def write_files(self, agent_id: UUID, files: dict[str, bytes], mode: str) -> int:
        """Write files to scratchpad. mode='replace' clears first. Returns total bytes."""

    @abstractmethod
    async def read_file(self, agent_id: UUID, path: str) -> bytes | None:
        """Read single file. Returns None if not found."""

    @abstractmethod
    async def list_files(self, agent_id: UUID) -> list[str]:
        """List all file paths."""

    @abstractmethod
    async def get_total_size(self, agent_id: UUID) -> int:
        """Total bytes used."""

    @abstractmethod
    async def clear(self, agent_id: UUID) -> None:
        """Delete all files, keep directory."""

    @abstractmethod
    async def delete_all(self, agent_id: UUID) -> None:
        """Remove storage entirely (agent destruction)."""
```

**FilesystemBackend (`filesystem.py`):**

- Base path from config: `settings.scratchpad_base_path` (default `/opt/mcpworks/scratchpad`)
- Agent directory: `{base_path}/{agent_id}/`
- **Atomic writes:** Write to `{base_path}/{agent_id}/.tmp-{uuid}/`, then `os.rename()` for replace mode. For append mode, write files directly.
- **Path validation (CTO-required symlink protection):**
  1. Parse with `pathlib.PurePosixPath`, reject `..` components
  2. Construct target: `agent_base / relative_path`
  3. Call `Path.resolve()` on the target to resolve any symlinks
  4. Re-verify resolved path starts with `agent_base.resolve()` prefix
  5. Reject if prefix check fails (symlink escape attempt)
- Reject absolute paths, null bytes, control characters. Max depth: 3 levels.
- **Size tracking:** Track size incrementally during writes. Use disk walk only for reconciliation (CTO recommendation). `write_files` returns bytes written; service layer updates `scratchpad_size_bytes` column by adding delta (replace mode) or by summing (append mode).
- Use `asyncio.to_thread()` for all filesystem I/O to avoid blocking the event loop

**Filename validation rules:**
- Regex: `^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,254}$`
- No `..` anywhere in path
- No absolute paths (starting with `/`)
- No null bytes or control characters
- Max path depth: 3 (e.g., `js/vendor/chart.min.js` is fine, `a/b/c/d/e.js` is not)
- Max 100 files per scratchpad

**Config addition (`config.py`):**
```python
scratchpad_base_path: str = "/opt/mcpworks/scratchpad"
scratchpad_max_files: int = 100
```

Quota is per-tier, resolved at runtime from the tier config, not a single global setting.

**Backend registration (`__init__.py`):**
```python
_backend: ScratchpadBackend | None = None

def get_scratchpad_backend() -> ScratchpadBackend:
    global _backend
    if _backend is None:
        from mcpworks_api.config import get_settings
        from mcpworks_api.scratchpad.filesystem import FilesystemBackend
        _backend = FilesystemBackend(get_settings().scratchpad_base_path)
    return _backend
```

**Single-writer constraint (CTO-required documentation):**
The FilesystemBackend assumes a single API process writes to each agent's directory. On k3s with a single node, a `ReadWriteOnce` PVC is sufficient. If scaling to multi-replica, the R2 backend becomes mandatory. This is documented here and in the k3s migration notes.

### Task 1.2: Database Migration — Agent Scratchpad Columns

**Migration:** `alembic revision --autogenerate -m "Add scratchpad columns to agents"`

**Changes to `src/mcpworks_api/models/agent.py`:**

```python
class Agent(Base, UUIDMixin, TimestampMixin):
    # ... existing fields ...
    scratchpad_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scratchpad_size_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
```

**Token generation utility:**
```python
import secrets
import base64

def generate_scratchpad_token() -> str:
    """Generate a 32-byte URL-safe base64 token (43 characters)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
```

Note: Token is 43 characters. VARCHAR(64) provides headroom for future format changes.

**Index:** Add partial unique index on `scratchpad_token` for fast lookup during view serving:
```python
Index("ix_agents_scratchpad_token", "scratchpad_token", unique=True,
      postgresql_where=text("scratchpad_token IS NOT NULL"))
```

No backfill needed. Existing agents get `scratchpad_token = NULL`. Token generated lazily on first `publish_view`.

---

## Phase 2: MCP Tools

### Task 2.1: Scratchpad Service Layer

**New file:** `src/mcpworks_api/services/scratchpad.py`

This service encapsulates all scratchpad business logic. Used by MCP tools (A0) and REST endpoints (A1).

```python
class ScratchpadService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.backend = get_scratchpad_backend()

    async def publish(
        self, agent: Agent, files: dict[str, str], mode: str = "replace"
    ) -> dict:
        """Publish files to agent's scratchpad. Returns url, files_written, total_bytes, quota_remaining_bytes."""

    async def get_url(self, agent: Agent) -> dict:
        """Get view URL and file listing."""

    async def clear(self, agent: Agent) -> None:
        """Clear all scratchpad content."""

    async def read_file(self, agent_id: UUID, path: str) -> bytes | None:
        """Read a file for serving (called by view endpoint)."""

    async def resolve_agent_by_token(self, token: str) -> Agent | None:
        """Look up agent by scratchpad token (for view serving)."""

    def _ensure_token(self, agent: Agent) -> str:
        """Lazily generate token if not set."""

    def _build_url(self, agent_name: str, token: str) -> str:
        """Build full view URL."""

    def _validate_filenames(self, filenames: list[str]) -> None:
        """Validate all filenames. Raise ValidationError on failure."""

    def _decode_file_content(self, content: str) -> bytes:
        """Decode string content. Handle 'base64:...' prefix for binary.
        Raise ValidationError on malformed base64."""

    def _get_quota_bytes(self, tier: str) -> int:
        """Return quota in bytes for the given tier."""

    def _check_quota(self, agent: Agent, new_bytes: int, mode: str, tier: str) -> None:
        """Check if write would exceed tier quota. Raise QuotaExceededError."""
```

**Publish flow:**
1. Check tier — Trial agents get 403 (scratchpad not available)
2. Validate all filenames
3. Decode all file contents (handle `base64:` prefix for binary; reject malformed base64 with 400)
4. Calculate total new bytes
5. Get tier quota via `_get_quota_bytes()`
6. Check quota (for replace: new_bytes <= max; for append: current + new_bytes <= max)
7. Ensure agent has a scratchpad token (generate if null)
8. Call `backend.write_files(agent_id, decoded_files, mode)`
9. Update `agent.scratchpad_size_bytes` incrementally (not disk walk)
10. Record `scratchpad_updated_at` timestamp on agent (for `X-Scratchpad-Updated` header)
11. Commit DB changes
12. Return URL + stats

### Task 2.2: MCP Tool Registration

**File to modify:** `src/mcpworks_api/mcp/protocol.py` (or wherever create-handler tools are registered)

Register **3 tools** on the **create** interface (rotate_view_token deferred to A1):

**`publish_view`** — write scope required
- Input: `agent_name` (string), `files` (object), `mode` (string, optional, default "replace")
- Calls `ScratchpadService.publish()`
- Response: `{url, files_written, total_bytes, quota_remaining_bytes}`

**`get_view_url`** — read scope required
- Input: `agent_name` (string)
- Calls `ScratchpadService.get_url()`
- Response: `{url, files, total_bytes}` or `{url: null, files: [], total_bytes: 0}`

**`clear_view`** — write scope required
- Input: `agent_name` (string)
- Calls `ScratchpadService.clear()`
- Response: `{status: "cleared"}`

**Tool tier classification:**
- `publish_view`, `clear_view` → builder tier
- `get_view_url` → standard tier

### Task 2.3: Update `describe_agent` Tool

Add `view_url` field to the agent description response when a scratchpad token exists and files are present:

```python
if agent.scratchpad_token and agent.scratchpad_size_bytes > 0:
    response["view_url"] = f"https://{agent.name}.agent.mcpworks.io/view/{agent.scratchpad_token}/"
    response["scratchpad_size_bytes"] = agent.scratchpad_size_bytes
```

---

## Phase 3: View Serving

### Task 3.1: View Serving Route + Rate Limiting

**New file:** `src/mcpworks_api/api/v1/scratchpad_view.py`

This handles the public (no auth) view serving on `*.agent.mcpworks.io`.

```python
router = APIRouter(tags=["scratchpad-view"])

@router.get("/view/{token}/{path:path}")
@router.get("/view/{token}/")
async def serve_scratchpad(token: str, path: str = "index.html", request: Request):
    """Serve scratchpad content. Public endpoint — token IS the auth."""
```

**Implementation:**

1. **Rate limit check** (CTO-required): Per-IP Redis rate limit, 60 requests/minute on `/view/` paths. Use existing `RateLimitMiddleware` pattern with a dedicated bucket: `scratchpad_view:{ip}:{minute}`. Return 429 with `Retry-After: 60` if exceeded.
2. Look up agent by `scratchpad_token` (indexed query)
3. If no agent found → 404
4. Verify the request hostname matches `{agent.name}.agent.mcpworks.io` (prevent token reuse across agents). In local dev, skip hostname check.
5. Validate `path` (same filename rules as publish, prevent traversal)
6. Read file from backend
7. If file not found → 404
8. Determine MIME type from extension
9. Return `Response(content=file_bytes, media_type=mime_type, headers=security_headers)`

**MIME type mapping:**

```python
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".map": "application/json; charset=utf-8",
}
```

Unknown extensions → `application/octet-stream`

**Security headers on every scratchpad response:**

```python
SCRATCHPAD_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "connect-src 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-cache, must-revalidate",
}
```

Plus dynamic header: `X-Scratchpad-Updated: {ISO 8601 timestamp}` from the agent's last publish time.

Note: `'unsafe-eval'` in CSP is an accepted risk for A0 (chart libraries may use eval). Revisit in A1 (CTO).

**Router mount order in `main.py` (CTO-required):**

The scratchpad view router MUST be mounted before the webhook router at the app level. Both respond on agent subdomains, but different path prefixes:

```python
# In main.py — order matters for agent subdomain routing
app.include_router(scratchpad_view_router)  # /view/{token}/... — FIRST
app.include_router(webhook_router)           # /webhook/{path}  — SECOND
```

The SubdomainMiddleware sets `request.state.endpoint_type = EndpointType.AGENT` for agent subdomains. Both routers check this. FastAPI matches routes by specificity — `/view/` prefix won't conflict with `/webhook/` prefix.

---

## Phase 4: Integration & Cleanup

### Task 4.1: Agent Destruction Cleanup + Docker Volume

**File to modify:** `src/mcpworks_api/services/agent_service.py`

In the `destroy_agent` method, add scratchpad cleanup before database deletion:

```python
async def destroy_agent(self, agent: Agent) -> None:
    # ... existing cleanup ...
    backend = get_scratchpad_backend()
    await backend.delete_all(agent.id)
    # ... existing DB deletion ...
```

**File to modify:** `docker-compose.prod.yml`

Add scratchpad volume to the API container:

```yaml
services:
  api:
    volumes:
      - scratchpad-data:/opt/mcpworks/scratchpad

volumes:
  scratchpad-data:
    driver: local
```

---

## Implementation Order & Dependencies

```
Phase 1 (foundation — no user-visible changes)
  Task 1.1: Backend interface + filesystem impl      [no dependencies]
  Task 1.2: Database migration                        [no dependencies]
  ── both can run in parallel ──

Phase 2 (MCP tools — agents can now publish)
  Task 2.1: Service layer                             [depends on 1.1, 1.2]
  Task 2.2: MCP tool registration (3 tools)           [depends on 2.1]
  Task 2.3: Update describe_agent                     [depends on 1.2]
  ── 2.2 and 2.3 can run in parallel after 2.1 ──

Phase 3 (serving — published content visible in browser)
  Task 3.1: View serving route + rate limiting        [depends on 2.1]

Phase 4 (integration)
  Task 4.1: Agent destruction cleanup + Docker volume [depends on 1.1]
```

---

## Files Changed Summary

| File | Change Type | Phase |
|------|-------------|-------|
| `src/mcpworks_api/scratchpad/__init__.py` | New | 1.1 |
| `src/mcpworks_api/scratchpad/base.py` | New | 1.1 |
| `src/mcpworks_api/scratchpad/filesystem.py` | New | 1.1 |
| `src/mcpworks_api/models/agent.py` | Modify (2 columns) | 1.2 |
| `src/mcpworks_api/config.py` | Modify (2 settings) | 1.1 |
| `alembic/versions/xxx_add_scratchpad.py` | New (auto) | 1.2 |
| `src/mcpworks_api/services/scratchpad.py` | New | 2.1 |
| `src/mcpworks_api/schemas/scratchpad.py` | New | 2.1 |
| `src/mcpworks_api/mcp/protocol.py` | Modify (3 tools) | 2.2 |
| `src/mcpworks_api/core/tool_permissions.py` | Modify (3 tools added) | 2.2 |
| `src/mcpworks_api/api/v1/scratchpad_view.py` | New | 3.1 |
| `src/mcpworks_api/main.py` | Modify (mount router) | 3.1 |
| `src/mcpworks_api/services/agent_service.py` | Modify (destroy cleanup) | 4.1 |
| `docker-compose.prod.yml` | Modify (volume) | 4.1 |

**New files:** 6
**Modified files:** 7

---

## Deferred to A1

| Item | Reason |
|------|--------|
| `rotate_view_token` MCP tool | CEO + CPO: reduce scope, ship 3 tools not 4 |
| REST API endpoints (`/v1/agents/{id}/scratchpad`) | CFO: MCP tools are primary interface |
| Channel auto-post on publish | CEO: reduces integration surface |
| Caddy static file serving (bypass FastAPI) | CTO: first A1 performance optimization |
| Per-tier quota differentiation beyond config | CFO: implement when usage data exists |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Filesystem storage lost during k3s migration | Medium | Low | Scratchpads are ephemeral. Agents republish. Document: "scratchpads cleared during migration." |
| Agents publishing malicious HTML (phishing) | Medium | Medium | CSP headers. X-Robots-Tag noindex. Scratchpad on `*.agent.mcpworks.io`, isolated from `api.mcpworks.io`. Admin kill switch (direct DB). ToS covers abuse. |
| Path traversal / symlink bypass | Low | High | Regex + PurePosixPath + `Path.resolve()` + prefix re-check after resolution. Security tests. |
| Disk space exhaustion from many agents | Low | Medium | Per-tier quota caps. Monitor disk usage. |
| Concurrent publish race condition | Low | Low | Atomic rename for replace mode. Last-write-wins is acceptable. |

---

## k3s Migration Notes

**Single-writer constraint:** The FilesystemBackend assumes a single API process writes to each agent's directory. On k3s with a single node, a `ReadWriteOnce` PVC is sufficient. Multi-replica requires the R2 backend.

When migrating from DigitalOcean droplet to k3s:

1. **Storage:** Replace Docker named volume with PersistentVolumeClaim. Mount at same path (`/opt/mcpworks/scratchpad`). Zero code changes.
2. **Config:** `SCRATCHPAD_BASE_PATH` env var overrides the default if needed.
3. **Data:** Scratchpads are ephemeral. No data migration required. Agents will republish on next cycle.
4. **Future:** When R2 backend is ready, set `SCRATCHPAD_BACKEND=r2` and provide R2 credentials. The `FilesystemBackend` is never touched again.

---

## Changelog

**v2.0.0 (2026-03-18):**
- Incorporated all board review feedback (CEO, CTO, CPO, CFO)
- Reduced to 6 tasks (deferred rotate_view_token, REST endpoints, channel auto-post)
- Added Path.resolve() symlink protection (CTO)
- Added per-IP rate limiting on /view/ (CTO)
- Added X-Robots-Tag and X-Scratchpad-Updated headers (CPO)
- Aligned scratchpad quotas with PRICING.md tiers (CFO)
- Documented single-writer constraint for k3s (CTO)
- Specified router mount order in main.py (CTO)

**v1.0.0 (2026-03-18):**
- Initial plan based on spec `agent-visual-scratchpad.md`
