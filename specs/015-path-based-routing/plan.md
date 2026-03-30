# Implementation Plan: Path-Based Routing

**Spec**: [015-path-based-routing/spec.md](spec.md)
**Created**: 2026-03-30
**Status**: Draft

## Architecture Overview

### Current Flow (Subdomain)

```
Client → acme.create.mcpworks.io/mcp
       → Caddy (wildcard TLS) → API :8000
       → SubdomainMiddleware extracts namespace="acme", endpoint="create"
       → MCPTransportMiddleware intercepts /mcp path
       → MCP handlers read request.state.namespace, request.state.endpoint_type
```

### New Flow (Path-Based)

```
Client → api.mcpworks.io/mcp/create/acme
       → Caddy (single cert) → API :8000
       → PathRoutingMiddleware extracts namespace="acme", endpoint="create"
       → MCPTransportMiddleware intercepts /mcp/* paths
       → MCP handlers read request.state.namespace, request.state.endpoint_type
         (unchanged — same request.state contract)
```

The key insight: **everything downstream of `request.state` is unchanged**. The refactor is entirely in how `request.state.namespace` and `request.state.endpoint_type` get populated.

## Technical Approach

### Phase 1: Path Extraction Middleware (replaces SubdomainMiddleware)

Create `middleware/routing.py` that:

1. Matches requests to `/mcp/{endpoint}/{namespace}` and `/mcp/{endpoint}/{namespace}/{subpath:path}`
2. Sets `request.state.namespace` and `request.state.endpoint_type` (same contract as SubdomainMiddleware)
3. Rewrites `request.scope["path"]` so downstream sees `/mcp` (preserving MCPTransportMiddleware compatibility) or the appropriate sub-path for agent routes

**Path patterns to handle:**

| Pattern | Meaning |
|---------|---------|
| `POST /mcp/create/{ns}` | MCP create endpoint |
| `POST /mcp/run/{ns}` | MCP run endpoint |
| `POST /mcp/agent/{ns}` | MCP agent endpoint |
| `GET /mcp/create/{ns}` | MCP SSE reconnection |
| `GET /mcp/run/{ns}` | MCP SSE reconnection |
| `DELETE /mcp/create/{ns}` | MCP session termination |
| `POST /mcp/agent/{ns}/webhook/{path}` | Agent webhook ingress |
| `POST /mcp/agent/{ns}/chat/{token}` | Agent public chat |
| `GET /mcp/agent/{ns}/view/{token}/` | Agent scratchpad view |
| `GET /mcp` | Discovery endpoint |

### Phase 2: Config Toggle

Add `ROUTING_MODE` setting to `config.py`:

```python
routing_mode: Literal["path", "subdomain", "both"] = Field(
    default="path",
    description="URL routing strategy: path (/mcp/create/ns), subdomain (ns.create.domain), or both",
)
```

- `path` (default): Only PathRoutingMiddleware is active. SubdomainMiddleware is not added.
- `subdomain`: Only SubdomainMiddleware is active (legacy behavior).
- `both`: Both are active. PathRouting takes precedence; SubdomainMiddleware is fallback for requests that arrive via wildcard DNS.

### Phase 3: URL Builder Update

Update `url_builder.py` to generate path-based URLs:

```python
# ROUTING_MODE=path (new default)
create_url("acme")  → "https://api.mcpworks.io/mcp/create/acme"
run_url("acme")     → "https://api.mcpworks.io/mcp/run/acme"
agent_url("mybot")  → "https://api.mcpworks.io/mcp/agent/mybot"
mcp_url("acme")     → "https://api.mcpworks.io/mcp/run/acme"

# ROUTING_MODE=subdomain (backward compat)
create_url("acme")  → "https://acme.create.mcpworks.io"
run_url("acme")     → "https://acme.run.mcpworks.io"
```

### Phase 4: MCPTransportMiddleware Update

Currently intercepts requests where `path == "/mcp"`. Must be updated to intercept:

- `/mcp/create/{ns}` (exact: 3 segments)
- `/mcp/run/{ns}` (exact: 3 segments)
- `/mcp/agent/{ns}` (exact: 3 segments)

But NOT:
- `/mcp/agent/{ns}/webhook/*` (these go to the webhook router)
- `/mcp/agent/{ns}/chat/*` (these go to the chat router)
- `/mcp/agent/{ns}/view/*` (these go to the scratchpad router)

The middleware can check: path starts with `/mcp/` AND has exactly 3 segments AND segment[1] is in `{create, run, agent}` AND there's no 4th segment (no sub-path).

### Phase 5: Agent Sub-Route Migration

Agent-specific routes currently mounted as:
- `webhooks.py` — matches `*/webhook/{path:path}` (relies on subdomain for namespace)
- `public_chat.py` — matches `*/chat/{token}` (relies on subdomain for namespace)
- `scratchpad_view.py` — matches `*/view/{token}/` (relies on subdomain for namespace)

These need dual mounting:
1. Under `/mcp/agent/{namespace}/webhook/...`, `/mcp/agent/{namespace}/chat/...`, `/mcp/agent/{namespace}/view/...` (path-based)
2. Keep existing routes for subdomain fallback (when `ROUTING_MODE=both|subdomain`)

### Phase 6: Documentation & Cleanup

- Update quickstart HTML
- Update tool descriptions in `tool_registry.py`
- Update CLAUDE.md and SPEC.md
- Update Caddy config documentation
- Add deprecation header to subdomain responses
- Update onboarding/console static pages

## Data Model Changes

None. This is a routing-only change. No database migrations required.

## API Contract Changes

### New Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/mcp/{endpoint}/{namespace}` | MCP JSON-RPC (create/run/agent) |
| GET | `/mcp/{endpoint}/{namespace}` | MCP SSE reconnection |
| DELETE | `/mcp/{endpoint}/{namespace}` | MCP session termination |
| POST | `/mcp/agent/{namespace}/webhook/{path:path}` | Agent webhook ingress |
| POST | `/mcp/agent/{namespace}/chat/{token}` | Agent public chat |
| GET | `/mcp/agent/{namespace}/view/{token}/` | Agent scratchpad view |
| GET | `/mcp` | MCP discovery |

### Deprecated Endpoints (transition period)

All subdomain-based access (`{ns}.{endpoint}.{domain}/mcp`, etc.) continues to work but returns `X-MCPWorks-Deprecated: subdomain-routing` header.

## File Change Map

| File | Change Type | Description |
|------|-------------|-------------|
| `middleware/routing.py` | **NEW** | Path-based routing middleware |
| `middleware/subdomain.py` | MODIFY | Add deprecation header; conditionally disabled |
| `middleware/__init__.py` | MODIFY | Export new middleware |
| `main.py` | MODIFY | Swap middleware based on `ROUTING_MODE` config |
| `config.py` | MODIFY | Add `routing_mode` setting |
| `url_builder.py` | MODIFY | Path-based URL generation |
| `mcp/transport.py` | MODIFY | Match `/mcp/{endpoint}/{ns}` paths |
| `api/v1/webhooks.py` | MODIFY | Support path-based namespace extraction |
| `api/v1/public_chat.py` | MODIFY | Support path-based namespace extraction |
| `api/v1/scratchpad_view.py` | MODIFY | Support path-based namespace extraction |
| `api/v1/health.py` | MODIFY | Remove wildcard DNS validation endpoint (or keep for transition) |
| `api/v1/quickstart.py` | MODIFY | Update URL examples |
| `mcp/tool_registry.py` | MODIFY | Update tool descriptions with path-based URLs |
| `mcp/router.py` | MODIFY | Update error messages |
| `static/console.html` | MODIFY | Update displayed URLs |
| `static/dashboard.html` | MODIFY | Update displayed URLs |
| `CLAUDE.md` | MODIFY | Update architecture docs |
| `SPEC.md` | MODIFY | Update endpoint docs |

## Testing Strategy

### Unit Tests

- `test_routing_middleware.py` — path parsing, edge cases (invalid endpoint, missing namespace, special chars)
- `test_url_builder.py` — URL generation for both routing modes

### Integration Tests

- Full MCP flow via path-based URL (initialize → tools/list → tools/call)
- Agent webhook delivery via path-based URL
- Agent chat via path-based URL
- Billing middleware correctly identifies `run` endpoint via path

### Backward Compatibility Tests

- Subdomain routing still works when `ROUTING_MODE=both`
- Deprecation header present on subdomain responses

## Rollback Plan

Set `ROUTING_MODE=subdomain` in environment. The entire path-based routing is bypassed. SubdomainMiddleware takes over exactly as before.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| MCPTransportMiddleware path matching breaks | Medium | High | Careful regex/prefix matching; comprehensive tests |
| Agent sub-routes don't mount correctly | Low | Medium | Test each route independently |
| URL builder returns wrong format | Low | Medium | Config-driven with tests for both modes |
| Existing users break during transition | Low | Low | `ROUTING_MODE=both` as intermediate step |

## Plan Completeness Checklist

- [x] All spec requirements mapped to technical approach
- [x] Architecture described
- [x] No database schema changes needed
- [x] API contracts defined
- [x] Error handling strategy documented (same as current — request.state contract unchanged)
- [x] Testing strategy defined
- [x] Rollback procedure defined
- [x] Security review completed (path traversal mitigated by namespace validation)
- [x] Token efficiency analysis completed (no impact)
