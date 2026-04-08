# Security Requirements

## Port Restrictions

**Allowed ports (no restrictions):**
- 80 (HTTP), 443 (HTTPS), 22 (SSH - managed access only)

**Allowed with justification:**
- 3000-3010 (dev servers), 5432 (PostgreSQL), 6379 (Redis), 27017 (MongoDB)

**Blocked (security risk):**
- 25, 587, 465 (SMTP - prevent spam)
- 23 (Telnet - insecure)
- 3389 (RDP - Windows attack vector)

## Input Validation

All tool inputs must:
- Validate against Pydantic schemas
- Sanitize for SQL injection
- Check for command injection
- Validate domain/DNS format
- Rate limit per account

## Authentication

**MCP Protocol:**
- API key authentication
- Session management
- Token rotation

**REST API:**
- JWT tokens
- OAuth2 for integrations
- API key for programmatic access
