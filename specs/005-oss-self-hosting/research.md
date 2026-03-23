# Research: Open-Source Self-Hosting Readiness

**Date**: 2026-03-22
**Branch**: `005-oss-self-hosting`

## R1: Domain Hardcoding Pattern

**Decision**: Add `base_domain` setting to `Settings` class, create `url_builder` utility module, thread through all 27+ hardcoded locations.

**Rationale**: All domain references use the same pattern: `f"https://{name}.{type}.mcpworks.io"`. A single `base_domain` config + centralized URL builder eliminates all hardcoding with minimal code change per site.

**Alternatives considered**:
- Per-component domain overrides (too complex, 9+ settings for the same domain)
- Request-based domain detection from Host header (fragile, doesn't work for background tasks/emails)

**Findings**:
- 13 source files contain hardcoded `mcpworks.io` URL patterns
- Static HTML files (console, dashboard, admin) fetch domain info via JS API calls — no hardcoded domains in HTML
- Email templates use Jinja2 with `autoescape=True` — can inject `base_url` as template variable
- `SubdomainMiddleware.__init__` already accepts `domain` parameter — just needs wiring to settings
- Namespace model has computed properties (`create_endpoint`, `run_endpoint`) — need settings access

## R2: Billing Bypass Pattern

**Decision**: Check `settings.stripe_secret_key` truthiness at middleware init; if empty, set a `billing_enabled` flag that skips all checks in `dispatch()`.

**Rationale**: BillingMiddleware already has `TIER_LIMITS` dict and checks user tier. Adding an early return when Stripe is unconfigured is a 5-line change. Tier execution limits are already in Settings (`tier_executions_*`).

**Alternatives considered**:
- Remove middleware entirely when Stripe absent (requires conditional middleware registration, complicates main.py)
- Create a NoBillingMiddleware subclass (over-engineered for a flag check)

**Findings**:
- BillingMiddleware has hardcoded rate limits (EXECUTIONS_PER_MINUTE, MAX_CONCURRENT, DAILY_COMPUTE_BUDGETS) — these should also be bypassed when billing disabled
- Account endpoints (`/v1/account`, `/v1/subscriptions`) need graceful responses when Stripe absent

## R3: Email Provider Abstraction

**Decision**: Add `SmtpProvider` implementing existing `EmailProvider` protocol. Update `_get_provider()` selection logic: Resend → SMTP → ConsoleProvider.

**Rationale**: Email service already uses protocol-based abstraction with `EmailProvider`. Adding SMTP is a new class implementing the same `send()` method. Provider selection in `_get_provider()` is the only change point.

**Alternatives considered**:
- Use a third-party email abstraction library (unnecessary dependency for SMTP support)
- Make email provider a plugin (over-engineered for 3 providers)

**Findings**:
- `EmailProvider` protocol: `async def send(self, to: str, subject: str, html: str) -> str | None`
- `ResendProvider` uses httpx, `ConsoleProvider` logs to structlog
- 13 email templates in Jinja2 format with `base.html` parent
- Fire-and-forget pattern via `asyncio.create_task()` with 3-attempt retry

## R4: Registration Control

**Decision**: Add `allow_registration` boolean setting (default: `True` for backward compat on Cloud, overridden to `False` in `.env.self-hosted.example`).

**Rationale**: Registration endpoint (`POST /v1/auth/register`) already exists. Adding a setting check at the top of the handler is a 3-line change. Default `True` maintains backward compat for MCPWorks Cloud.

**Findings**:
- Registration handler in `api/v1/auth.py`
- Current flow: validate input → check email uniqueness → create user → send welcome email
- Self-hosted default should be `False` (set in `.env.self-hosted.example`)

## R5: BSL 1.1 License

**Decision**: Use standard BSL 1.1 template text with parameters: Licensor = MCPWorks Inc., Change Date = 2030-03-22 (4 years from now), Change License = Apache License 2.0.

**Rationale**: Industry standard for source-available projects (MariaDB, CockroachDB, Sentry). 4-year change date balances commercial protection with community trust.

**Findings**:
- BSL 1.1 text available from mariadb.com/bsl11
- Additional Use Grant should specify: "Production use for internal business purposes"
- pyproject.toml already updated to `license = {text = "BSL-1.1"}`

## R6: Caddyfile Templating

**Decision**: Create `Caddyfile.self-hosted` template with `{$BASE_DOMAIN}` environment variable substitution (Caddy's native env var syntax).

**Rationale**: Caddy natively supports `{$ENV_VAR}` syntax in Caddyfile. No preprocessing needed — just set the env var and Caddy substitutes on startup.

**Alternatives considered**:
- sed/envsubst preprocessing (unnecessary, Caddy has native support)
- Caddy API-based config (more complex, less readable)

**Findings**:
- Current Caddyfile: 4 server blocks (api, *.create, *.run, *.agent)
- On-demand TLS with internal verification endpoint (`/v1/internal/verify-domain`)
- WireGuard binding for admin access (optional for self-hosted)

## R7: Self-Hosted Docker Compose

**Decision**: Create `docker-compose.self-hosted.yml` with postgres:15, redis:7, api (from Dockerfile), and caddy (from Caddyfile.self-hosted).

**Rationale**: Self-hosters need a single file that brings up everything. Dev compose lacks Caddy/TLS. Prod compose expects external managed services.

**Findings**:
- Dev compose: postgres + redis + api (port 8001)
- Prod compose: caddy + api (expects external postgres/redis)
- Self-hosted needs: postgres + redis + caddy + api (all-in-one)
- API startup script (`scripts/start.sh`) already handles migration and DB wait
