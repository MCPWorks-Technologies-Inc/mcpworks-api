# Changelog

All notable changes to MCPWorks API will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
