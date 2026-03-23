# Quickstart: Open-Source Self-Hosting Implementation

**Branch**: `005-oss-self-hosting`

## Implementation Order

This feature should be implemented in this order to minimize risk and enable incremental testing:

### Step 1: URL Builder + Config (foundation)
1. Add `base_domain`, `base_scheme` to `Settings` in `config.py`
2. Create `src/mcpworks_api/url_builder.py` with all URL construction functions
3. Write unit tests for url_builder with various domain configs

### Step 2: Thread base_domain through source (the bulk)
4. Update `middleware/subdomain.py` to use `settings.base_domain`
5. Update `models/namespace.py` properties to use url_builder
6. Update MCP handlers (code_mode, code_mode_ts, run_handler, create_handler)
7. Update services (agent_service, scratchpad)
8. Update API routes (health, llm, scratchpad_view, public_chat, webhooks)
9. Update `main.py` admin domain check
10. Write integration tests verifying custom domain URL generation

### Step 3: Registration control
11. Add `allow_registration` to Settings
12. Add registration gate in auth handler
13. Write test for registration disabled/enabled

### Step 4: Billing bypass
14. Add billing-disabled detection to BillingMiddleware
15. Update account/subscription endpoints for self-hosted mode
16. Write tests for billing-disabled flow

### Step 5: SMTP email provider
17. Create SmtpProvider implementing EmailProvider protocol
18. Update `_get_provider()` selection logic
19. Pass `base_url` to email templates
20. Write tests for provider selection and SMTP send

### Step 6: LICENSE + deployment files
21. Create LICENSE file (BSL 1.1)
22. Create `docker-compose.self-hosted.yml`
23. Create `Caddyfile.self-hosted`
24. Create `.env.self-hosted.example`
25. Create `scripts/seed_admin.py`
26. Update README with license badge and self-hosting link

### Step 7: Documentation
27. Write `docs/SELF-HOSTING.md`

## Verification

After implementation, verify SC-002 by running:
```bash
grep -r "mcpworks\.io" src/ --include="*.py" | grep -v "test" | grep -v "__pycache__"
```
Any remaining hits should be in comments, default values (with override), or archive/test files only. Zero hardcoded runtime references.

## Risk Areas

- **Namespace model properties**: These are used throughout the codebase. Importing `get_settings()` in a model file creates a potential circular import. url_builder module avoids this by being a standalone utility.
- **Email template variables**: Adding `base_url` to all `send_email()` calls requires updating every convenience wrapper. The Jinja2 environment can inject it globally via `globals`.
- **Backward compatibility**: Default `base_domain=mcpworks.io` ensures MCPWorks Cloud is unaffected. Must verify no tests assume the default and break.
