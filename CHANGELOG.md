# Changelog

All notable changes to MCPWorks API will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-26

### Added
- **Namespace Git Export/Import** — export namespaces to any Git remote (GitHub, GitLab, Gitea, Bitbucket), import from any Git URL. YAML + code directory structure. Provider-agnostic via HTTPS + PAT.
- **Third-Party MCP Server Plugins** — bolt any MCP server onto your namespace. Tools callable from the code sandbox via internal proxy. Credentials encrypted, never in sandbox. LLM-tunable settings and env vars per server.
- **Prompt Injection Defense** — mandatory `output_trust` on functions, trust boundary markers on untrusted output, pattern-based injection scanner with text normalization (base64, Unicode, zero-width), per-MCP-server request/response rules engine.
- **Canary Tokens** — random canary injected into agent system prompts. Tool calls checked for canary leakage. Immediate halt on detection.
- **MCP Server Schema Diffing** — tool schema hashes stored on registration, compared on refresh. Detects tool mutation attacks.
- **MCP Proxy Analytics** — per-call telemetry (latency, response size, errors) stored in PostgreSQL. 4 analytics MCP tools: get_mcp_server_stats, get_token_savings_report, suggest_optimizations, get_function_mcp_stats.
- **Getting Started Tutorial** — zero to first function in 5 minutes
- **Versioning section** in README with pre-1.0 expectations

### Changed
- Dependencies updated: openai <3, structlog <26, node 25-slim, actions/checkout v6, actions/setup-python v6, codecov-action v5
- Self-hosting docs rewritten with correct JWT key paths and docker-compose references
- Branch protection enabled on main (required CI + review)
- speckit workflow integrated into PR template and CONTRIBUTING.md
- WireGuard subnet changed from 10.0.0.0/24 to 10.100.0.0/24

### Fixed
- Migration down_revision format (ID only, not filename suffix)
- FunctionService.create() missing output_trust parameter

### Removed
- Stray internal files (STYLE.md, admin-login-form.png, demo scripts, .env.production.example)
- Private key scrubbed from git history

### Security
- All production credentials rotated (PostgreSQL, JWT, SECRET_KEY, KEK, OAuth, Resend, Discord, ADMIN_API_KEY)
- KEK migration script recovered 33 encrypted DB entries
- CVE-2026-4539 (pygments) ignored in pip-audit (no fix available, local-only)

## [0.1.0] - 2026-03-23

### Added
- Initial open-source release under BSL 1.1
- Namespace-based function hosting with MCP protocol support
- Code execution sandbox (nsjail) with Python and TypeScript runtimes
- Autonomous agent runtime with scheduling, persistent state, and webhooks
- BYOAI support (Claude, GPT, Gemini, or any OpenAI-compatible provider)
- Discord integration for agent channels
- REST API for account management, authentication (JWT + OAuth2), and usage tracking
- Subscription-based billing via Stripe
- Docker Compose self-hosting with bundled PostgreSQL and Redis
- Caddy reverse proxy with automatic TLS and wildcard subdomain routing
- Envelope encryption (AES-256-GCM) for stored secrets
- Credential scanning for user-submitted code
- Comprehensive spec-driven development documentation
