# Tasks: Path-Based Routing

**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Created**: 2026-03-30

## Task 1: Add `routing_mode` config setting

**Estimated Effort**: 1 hour
**Dependencies**: None

### Acceptance Criteria
- [ ] `Settings.routing_mode` field added with type `Literal["path", "subdomain", "both"]`, default `"path"`
- [ ] `ROUTING_MODE` env var controls the setting
- [ ] Setting is accessible via `get_settings().routing_mode`

### Files
- `src/mcpworks_api/config.py`

---

## Task 2: Create `PathRoutingMiddleware`

**Estimated Effort**: 3 hours
**Dependencies**: Task 1

### Acceptance Criteria
- [ ] New file `middleware/routing.py` with `PathRoutingMiddleware`
- [ ] Parses `/mcp/{endpoint}/{namespace}` from request path
- [ ] Sets `request.state.namespace`, `request.state.endpoint_type`, `request.state.is_local`
- [ ] Validates endpoint is one of `create`, `run`, `agent`
- [ ] Validates namespace matches `[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?`
- [ ] Passes through requests that don't match `/mcp/*` (health, v1 API, static pages)
- [ ] Returns 404 for `/mcp/{invalid_endpoint}/{ns}`
- [ ] Returns 404 for `/mcp/{endpoint}/` (missing namespace)
- [ ] Agent sub-paths (`/mcp/agent/{ns}/webhook/*`, `/mcp/agent/{ns}/chat/*`, `/mcp/agent/{ns}/view/*`) set request.state but do NOT rewrite the path — they pass through to agent-specific routers
- [ ] `GET /mcp` passes through (discovery endpoint)
- [ ] Exported from `middleware/__init__.py`

### Files
- `src/mcpworks_api/middleware/routing.py` (new)
- `src/mcpworks_api/middleware/__init__.py`

---

## Task 3: Update `MCPTransportMiddleware` path matching

**Estimated Effort**: 2 hours
**Dependencies**: Task 2

### Acceptance Criteria
- [ ] `MCPTransportMiddleware` intercepts POST/GET/DELETE to `/mcp/{endpoint}/{namespace}` (3 path segments under /mcp/)
- [ ] Does NOT intercept agent sub-paths with 4+ segments (`/mcp/agent/{ns}/webhook/*`, etc.)
- [ ] Does NOT intercept `GET /mcp` (discovery)
- [ ] SSE reconnection (GET) works at `/mcp/{endpoint}/{namespace}`
- [ ] Session termination (DELETE) works at `/mcp/{endpoint}/{namespace}`
- [ ] Backward compat: still intercepts `/mcp` when `ROUTING_MODE=subdomain|both`

### Files
- `src/mcpworks_api/mcp/transport.py`

---

## Task 4: Update `url_builder.py`

**Estimated Effort**: 1.5 hours
**Dependencies**: Task 1

### Acceptance Criteria
- [ ] When `routing_mode == "path"`: `create_url("acme")` returns `https://api.mcpworks.io/mcp/create/acme`
- [ ] When `routing_mode == "path"`: `run_url("acme")` returns `https://api.mcpworks.io/mcp/run/acme`
- [ ] When `routing_mode == "path"`: `agent_url("mybot")` returns `https://api.mcpworks.io/mcp/agent/mybot`
- [ ] When `routing_mode == "path"`: `mcp_url("acme", "run")` returns `https://api.mcpworks.io/mcp/run/acme`
- [ ] When `routing_mode == "path"`: `view_url("mybot", "tok123")` returns `https://api.mcpworks.io/mcp/agent/mybot/view/tok123/`
- [ ] When `routing_mode == "path"`: `chat_url("mybot", "tok123")` returns `https://api.mcpworks.io/mcp/agent/mybot/chat/tok123`
- [ ] When `routing_mode == "subdomain"`: all functions return current subdomain-based URLs (no regression)
- [ ] `valid_suffixes()` updated or replaced with a path-aware equivalent

### Files
- `src/mcpworks_api/url_builder.py`

---

## Task 5: Wire middleware in `main.py`

**Estimated Effort**: 1 hour
**Dependencies**: Task 2

### Acceptance Criteria
- [ ] When `ROUTING_MODE=path`: `PathRoutingMiddleware` is added, `SubdomainMiddleware` is NOT added
- [ ] When `ROUTING_MODE=subdomain`: `SubdomainMiddleware` is added, `PathRoutingMiddleware` is NOT added
- [ ] When `ROUTING_MODE=both`: Both middlewares are added; `PathRoutingMiddleware` runs first (added last in FastAPI middleware stack) and only populates `request.state` if the path matches; `SubdomainMiddleware` fills in if path didn't match
- [ ] Middleware ordering preserved: Correlation → Logging → Routing → Rate Limit → Billing → Transport (innermost)

### Files
- `src/mcpworks_api/main.py`

---

## Task 6: Mount agent sub-routes under path-based prefix

**Estimated Effort**: 2 hours
**Dependencies**: Task 2

### Acceptance Criteria
- [ ] Webhook ingress works at `POST /mcp/agent/{namespace}/webhook/{path:path}`
- [ ] Public chat works at `POST /mcp/agent/{namespace}/chat/{token}`
- [ ] Scratchpad view works at `GET /mcp/agent/{namespace}/view/{token}/`
- [ ] Each handler extracts namespace from the path parameter (or from `request.state` set by middleware)
- [ ] Existing subdomain-based routes preserved when `ROUTING_MODE=subdomain|both`

### Files
- `src/mcpworks_api/api/v1/webhooks.py`
- `src/mcpworks_api/api/v1/public_chat.py`
- `src/mcpworks_api/api/v1/scratchpad_view.py`
- `src/mcpworks_api/main.py` (router mounting)

---

## Task 7: Update tool descriptions and quickstart docs

**Estimated Effort**: 1.5 hours
**Dependencies**: Task 4

### Acceptance Criteria
- [ ] `tool_registry.py` webhook/chat URL descriptions use `url_builder` (not hardcoded subdomain patterns)
- [ ] `quickstart.py` HTML updated to show path-based URL examples
- [ ] Error messages in `mcp/router.py` updated to reference path-based format

### Files
- `src/mcpworks_api/mcp/tool_registry.py`
- `src/mcpworks_api/api/v1/quickstart.py`
- `src/mcpworks_api/mcp/router.py`

---

## Task 8: Add deprecation header to subdomain responses

**Estimated Effort**: 0.5 hours
**Dependencies**: Task 2

### Acceptance Criteria
- [ ] When `SubdomainMiddleware` handles a request (i.e., namespace was extracted from subdomain, not path), the response includes `X-MCPWorks-Deprecated: subdomain-routing; migrate to /mcp/{endpoint}/{namespace}`
- [ ] Header is NOT added when `ROUTING_MODE=subdomain` (no deprecation when it's the only mode)

### Files
- `src/mcpworks_api/middleware/subdomain.py`

---

## Task 9: Add MCP discovery endpoint

**Estimated Effort**: 0.5 hours
**Dependencies**: Task 4

### Acceptance Criteria
- [ ] `GET /mcp` returns JSON with protocol version, supported endpoint types, and URL pattern template
- [ ] Response example: `{"protocol": "mcp", "version": "2024-11-05", "url_template": "/mcp/{endpoint}/{namespace}", "endpoints": ["create", "run", "agent"]}`

### Files
- `src/mcpworks_api/mcp/router.py` or new route in `main.py`

---

## Task 10: Write tests

**Estimated Effort**: 3 hours
**Dependencies**: Tasks 1-6

### Acceptance Criteria
- [ ] Unit tests for `PathRoutingMiddleware` — valid paths, invalid paths, edge cases
- [ ] Unit tests for `url_builder` — both routing modes
- [ ] Integration test: full MCP create flow via `/mcp/create/{ns}`
- [ ] Integration test: full MCP run flow via `/mcp/run/{ns}`
- [ ] Integration test: agent webhook via `/mcp/agent/{ns}/webhook/{path}`
- [ ] Integration test: billing middleware fires on `/mcp/run/{ns}` (endpoint_type == "run")
- [ ] Backward compat test: subdomain routing when `ROUTING_MODE=both`

### Files
- `tests/unit/test_routing_middleware.py` (new)
- `tests/unit/test_url_builder.py` (new or update)
- `tests/integration/test_path_routing.py` (new)

---

## Task 11: Update project documentation

**Estimated Effort**: 1 hour
**Dependencies**: Tasks 1-9

### Acceptance Criteria
- [ ] `CLAUDE.md` updated: architecture section reflects path-based routing as primary
- [ ] `SPEC.md` updated if it references subdomain patterns
- [ ] `CLAUDE.md` endpoint pattern changed from `{ns}.create.mcpworks.io` to `api.mcpworks.io/mcp/create/{ns}`
- [ ] Static HTML pages (console, dashboard, onboarding) updated if they display URLs

### Files
- `CLAUDE.md`
- `SPEC.md`
- `src/mcpworks_api/static/console.html`
- `src/mcpworks_api/static/dashboard.html`

---

## Execution Order

```
Task 1 (config)
  ├── Task 2 (PathRoutingMiddleware)
  │     ├── Task 3 (transport middleware update)
  │     ├── Task 5 (wire in main.py)
  │     ├── Task 6 (agent sub-routes)
  │     └── Task 8 (deprecation header)
  ├── Task 4 (url_builder)
  │     ├── Task 7 (tool descriptions & docs)
  │     └── Task 9 (discovery endpoint)
  └── Task 10 (tests — after 1-6)
       └── Task 11 (documentation — after all)
```

**Critical path**: Task 1 → Task 2 → Task 3 → Task 5 → Task 10

**Estimated total effort**: ~17 hours
