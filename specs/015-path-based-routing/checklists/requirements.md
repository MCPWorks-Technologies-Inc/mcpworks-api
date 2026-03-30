# Requirements Checklist: Path-Based Routing

## Functional Requirements

- [ ] FR-001: API accepts MCP requests at `/mcp/{endpoint}/{namespace}`
- [ ] FR-002: Path params populate `request.state` identically to SubdomainMiddleware
- [ ] FR-003: `url_builder` generates path-based URLs with config toggle
- [ ] FR-004: Agent sub-paths work under path-based scheme
- [ ] FR-005: SubdomainMiddleware remains functional when `ROUTING_MODE=subdomain|both`
- [ ] FR-006: All response URLs use path-based format when `ROUTING_MODE=path`
- [ ] FR-007: `GET /mcp` returns protocol discovery info

## Non-Functional Requirements

- [ ] NFR-001: Zero performance regression
- [ ] NFR-002: Self-host works with IP address only (no DNS/TLS)
- [ ] NFR-003: Single origin for all MCP traffic

## User Stories

- [ ] US-1: Self-hosted MCP connection via path-based URL
- [ ] US-2: Cloud MCP connection via path-based URL
- [ ] US-3: Backward compatibility with subdomain URLs (transition period)
- [ ] US-4: Agent webhooks/chat/view via path-based URLs

## Security

- [ ] Path traversal prevented by namespace validation regex
- [ ] Auth enforcement identical to subdomain routing
- [ ] No namespace enumeration beyond what DNS already exposes

## Testing

- [ ] Unit tests for PathRoutingMiddleware
- [ ] Unit tests for url_builder (both modes)
- [ ] Integration tests for MCP create/run flows
- [ ] Integration tests for agent sub-routes
- [ ] Backward compatibility tests
