# Feature Specification: Open-Source Self-Hosting Readiness

**Feature Branch**: `005-oss-self-hosting`
**Created**: 2026-03-22
**Status**: Draft
**Input**: User description: "Make mcpworks-api deployable as a clean open-source package via `docker compose up` on any Linux server."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Domain-Agnostic Deployment (Priority: P1)

A self-hosting operator clones the repository, sets `BASE_DOMAIN=example.com` in their environment, and all namespace endpoints, MCP URLs, email links, admin access, and static UI pages automatically reflect their custom domain. No source code modifications are required.

**Why this priority**: Without configurable domain support, the platform is unusable on any domain other than mcpworks.io. This is the single largest blocker for self-hosting — it affects subdomain routing, URL generation, admin access, email templates, and frontend assets.

**Independent Test**: Can be fully tested by deploying with a custom domain and verifying all generated URLs, email links, MCP endpoints, and admin panel access use the configured domain instead of mcpworks.io.

**Acceptance Scenarios**:

1. **Given** a fresh deployment with `BASE_DOMAIN=selfhost.dev`, **When** a user creates a namespace called "demo", **Then** the API returns `https://demo.create.selfhost.dev/mcp` and `https://demo.run.selfhost.dev/mcp` as the MCP endpoints.
2. **Given** `BASE_DOMAIN=selfhost.dev`, **When** a user accesses the admin panel at `https://api.selfhost.dev/admin`, **Then** admin access is granted (not rejected due to domain mismatch).
3. **Given** `BASE_DOMAIN=selfhost.dev`, **When** the system sends a welcome email, **Then** all links in the email point to `selfhost.dev` URLs (not mcpworks.io).
4. **Given** `BASE_DOMAIN=selfhost.dev`, **When** a user views the onboarding/dashboard/console pages, **Then** all displayed MCP endpoint URLs use `selfhost.dev`.
5. **Given** `BASE_DOMAIN=selfhost.dev`, **When** the health check endpoint validates subdomain suffixes, **Then** it accepts `.create.selfhost.dev`, `.run.selfhost.dev`, and `.agent.selfhost.dev` as valid.
6. **Given** no `BASE_DOMAIN` is set, **When** the application starts, **Then** it defaults to `mcpworks.io` (backward compatible with MCPWorks Cloud).

---

### User Story 2 - One-Command Self-Hosted Deployment (Priority: P1)

A developer clones the repository, copies the example environment file, generates keys, runs `docker compose up`, and has a fully functional MCPWorks instance running with local PostgreSQL, Redis, and Caddy — all on a single machine.

**Why this priority**: The promise of open-source is "clone and run." Without a self-contained deployment path, self-hosting requires cobbling together external services, which defeats the purpose.

**Independent Test**: Can be tested by running `docker compose -f docker-compose.self-hosted.yml up` on a fresh Linux server and verifying the health endpoint responds successfully.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the repository, **When** the operator copies `.env.self-hosted.example` to `.env`, generates JWT keys, and runs `docker compose -f docker-compose.self-hosted.yml up`, **Then** all services (postgres, redis, api, caddy) start and pass health checks within 3 minutes.
2. **Given** a running self-hosted deployment, **When** the operator runs the seed script, **Then** an initial admin account is created and the operator can log in.
3. **Given** a running self-hosted deployment, **When** the operator opens `https://api.<domain>/v1/health`, **Then** they receive a 200 OK response confirming database and cache connectivity.
4. **Given** the self-hosted compose file, **When** the operator examines it, **Then** it includes postgres, redis, api, and caddy services with no external service dependencies required for basic operation.

---

### User Story 3 - Billing-Optional Operation (Priority: P2)

A self-hosting operator who does not have a Stripe account can run the platform without billing enforcement. All users operate without execution limits, and the billing middleware is bypassed when Stripe is not configured.

**Why this priority**: Many self-hosters (internal teams, hobbyists, evaluators) don't need billing. Making Stripe mandatory blocks adoption for these users.

**Independent Test**: Can be tested by starting the platform without any Stripe environment variables and verifying that users can register, create functions, and execute them without encountering billing errors.

**Acceptance Scenarios**:

1. **Given** no Stripe API keys are configured, **When** a user executes a function, **Then** the execution succeeds without billing checks or limit enforcement.
2. **Given** no Stripe API keys are configured, **When** a user visits the account page, **Then** it shows "Self-hosted (no billing)" instead of subscription tier information.
3. **Given** Stripe API keys are later added to the environment, **When** the platform restarts, **Then** billing enforcement activates and subscription tiers are enforced.

---

### User Story 4 - Email Provider Flexibility (Priority: P3)

A self-hosting operator who does not use Resend can configure SMTP credentials instead, so that transactional emails (welcome, alerts, invitations) are sent via their own mail server or any SMTP-compatible service.

**Why this priority**: Resend is a SaaS dependency that requires an account and API key. Self-hosters need the option to use their own email infrastructure. However, the platform can function without email (users just won't receive notifications), so this is lower priority.

**Independent Test**: Can be tested by configuring SMTP credentials and triggering a welcome email, then verifying it arrives via the configured SMTP server.

**Acceptance Scenarios**:

1. **Given** SMTP credentials are configured (host, port, username, password, from address), **When** the platform sends a transactional email, **Then** the email is delivered via SMTP instead of Resend.
2. **Given** neither Resend nor SMTP credentials are configured, **When** the platform attempts to send an email, **Then** the email is silently skipped (logged but not errored), and the user-facing operation continues successfully.
3. **Given** Resend API key is configured, **When** the platform sends an email, **Then** behavior is unchanged from current production (Resend is used).

---

### User Story 5 - License and Legal Clarity (Priority: P1)

A developer evaluating the repository can immediately understand the licensing terms. The BSL 1.1 license text is present in the repository root, and the README clearly states the license.

**Why this priority**: Open-source without a LICENSE file is legally ambiguous. This is table stakes for any open-source project.

**Independent Test**: Can be tested by verifying the LICENSE file exists at the repository root and contains valid BSL 1.1 text.

**Acceptance Scenarios**:

1. **Given** a user clones the repository, **When** they look at the root directory, **Then** a LICENSE file is present containing the BSL 1.1 license text with MCPWorks-specific parameters filled in (licensor, change date, change license).
2. **Given** a user reads the README, **When** they look for license information, **Then** the license type and a link to the LICENSE file are clearly stated.

---

### User Story 6 - Self-Hosting Documentation (Priority: P2)

A system administrator who is unfamiliar with MCPWorks can follow a step-by-step guide to go from a fresh Linux server to a running MCPWorks instance, including DNS setup, key generation, environment configuration, and verification.

**Why this priority**: Documentation is the difference between "theoretically self-hostable" and "practically self-hostable." Without it, only developers who read the source code can deploy.

**Independent Test**: Can be tested by giving the documentation to someone unfamiliar with MCPWorks and having them complete a deployment without additional guidance.

**Acceptance Scenarios**:

1. **Given** a user reads `docs/SELF-HOSTING.md`, **When** they follow the instructions, **Then** they can complete a deployment from clone to running health check.
2. **Given** the documentation, **When** a user looks for prerequisites, **Then** they find a clear list of system requirements including Linux kernel version, Docker version, domain/DNS requirements, and hardware minimums.
3. **Given** the documentation, **When** a user wants to understand nsjail vs dev mode, **Then** they find a clear explanation of sandbox security modes, their trade-offs, and which to use for production vs testing.

---

### Edge Cases

- What happens when `BASE_DOMAIN` contains a port number (e.g., `localhost:8443` for local testing without DNS)? The system should handle port in URL generation but may not support wildcard subdomains.
- What happens when the operator uses HTTP instead of HTTPS (e.g., local development without TLS)? A `BASE_SCHEME` setting (default: `https`) should control protocol in generated URLs.
- What happens when the operator has an existing PostgreSQL or Redis instance? They should be able to set `DATABASE_URL` and `REDIS_URL` in their environment to point to external services.
- What happens when the operator runs on a non-Linux OS? The documentation should clearly state that `SANDBOX_DEV_MODE=true` must be used, with a warning that it provides no code isolation.
- What happens when the operator upgrades from one version to the next? Migrations run automatically on startup via Alembic, handling schema changes idempotently.
- What happens when the Caddyfile template is used without wildcard DNS configured? Caddy will fail to obtain wildcard TLS certificates; the documentation should explain DNS requirements.

## Requirements *(mandatory)*

### Functional Requirements

**Domain Configuration:**
- **FR-001**: System MUST accept a `BASE_DOMAIN` configuration setting that controls all generated URLs, subdomain routing, admin access validation, and email link generation.
- **FR-002**: System MUST default `BASE_DOMAIN` to `mcpworks.io` when not explicitly configured (backward compatible).
- **FR-003**: All namespace endpoint URLs (create, run, agent) MUST be dynamically generated using `BASE_DOMAIN`.
- **FR-004**: Admin panel access MUST be granted based on the configured `BASE_DOMAIN`, not a hardcoded domain list.
- **FR-005**: Health check subdomain validation MUST accept suffixes derived from `BASE_DOMAIN`.
- **FR-006**: Email templates MUST use `BASE_DOMAIN` for all hyperlinks and branding references.
- **FR-007**: Static HTML pages (onboarding, dashboard, console) MUST display URLs derived from `BASE_DOMAIN`.
- **FR-008**: JWT issuer and audience claims MUST use `BASE_DOMAIN` by default (overridable via separate config).
- **FR-009**: CORS origins MUST include the configured `BASE_DOMAIN` and its subdomains by default.

**Self-Hosted Deployment:**
- **FR-010**: A self-hosted Docker Compose file MUST include PostgreSQL, Redis, API, and Caddy services with no external dependencies required.
- **FR-011**: A Caddyfile template MUST be provided that uses `BASE_DOMAIN` for routing configuration.
- **FR-012**: An example environment file (`.env.self-hosted.example`) MUST document all required and optional environment variables with descriptions.
- **FR-013**: A seed script MUST create an initial admin account when run against a fresh database.
- **FR-014**: Database migrations MUST run automatically on container startup.

**Billing Optionality:**
- **FR-015**: System MUST operate without Stripe when no Stripe API keys are configured.
- **FR-016**: When Stripe is not configured, all billing middleware MUST be bypassed and execution limits MUST NOT be enforced.
- **FR-017**: When Stripe is not configured, account/subscription endpoints MUST return a "self-hosted" status instead of erroring.

**Email Flexibility:**
- **FR-018**: System MUST support SMTP as an alternative email transport when Resend is not configured.
- **FR-019**: When neither Resend nor SMTP is configured, email operations MUST fail silently (logged, not errored).

**License:**
- **FR-020**: Repository MUST contain a LICENSE file with BSL 1.1 text at the root.
- **FR-021**: README MUST reference the license type and link to the LICENSE file.

**Documentation:**
- **FR-022**: A self-hosting guide (`docs/SELF-HOSTING.md`) MUST cover prerequisites, setup, configuration, verification, and troubleshooting.
- **FR-023**: Documentation MUST explain the difference between nsjail (production) and `SANDBOX_DEV_MODE` (testing), including system requirements for each.

### Key Entities

- **Deployment Configuration**: The set of environment variables and files that define a self-hosted instance (domain, database URL, redis URL, keys, optional billing, optional email).
- **Base Domain**: The root domain that controls all URL generation, routing, and access validation across the platform.
- **Email Transport**: The abstraction layer for sending transactional emails (Resend API, SMTP, or disabled).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can go from `git clone` to a running, healthy MCPWorks instance in under 15 minutes by following the self-hosting guide.
- **SC-002**: 100% of generated URLs (namespace endpoints, email links, admin pages, static assets) use the configured custom domain — zero hardcoded mcpworks.io references in runtime output.
- **SC-003**: The platform starts and serves requests successfully with zero external service dependencies (no Stripe, no Resend, no managed databases).
- **SC-004**: Existing MCPWorks Cloud deployments continue to function identically with no configuration changes (full backward compatibility).
- **SC-005**: All 23 functional requirements have corresponding automated or manual test cases that pass.
- **SC-006**: The self-hosting guide is complete enough that a system administrator unfamiliar with MCPWorks can deploy the platform without reading source code.

## Assumptions

- Self-hosters will use Linux for production deployments (nsjail requires Linux kernel features). macOS/Windows users can use `SANDBOX_DEV_MODE=true` for evaluation only.
- Self-hosters will manage their own DNS (wildcard records pointing `*.create.<domain>`, `*.run.<domain>`, `*.agent.<domain>` to their server).
- The existing `docker-compose.yml` (development) is not suitable for self-hosted production use because it lacks Caddy, uses test credentials, and doesn't configure TLS.
- Self-hosters who don't configure email will accept that users won't receive welcome emails, alerts, or invitation links.
- Self-hosters who don't configure Stripe will accept that all users operate without billing limits.
- The Caddyfile template will use automatic HTTPS via Let's Encrypt, requiring the server to be publicly accessible on port 80/443 for certificate issuance.
- Database migrations are safe to run automatically on startup (idempotent via Alembic's revision tracking).

## Scope Boundaries

**In scope:**
- Domain configuration and hardcoded URL refactoring
- Self-hosted Docker Compose with bundled services
- Caddyfile template
- Environment file examples
- Admin seed script
- BSL 1.1 LICENSE file
- Self-hosting documentation
- Stripe-optional mode
- SMTP email fallback

**Out of scope:**
- Kubernetes / Helm chart deployment (future work)
- GUI-based installer or setup wizard
- Automatic DNS provisioning
- Multi-node / high-availability self-hosted configurations
- Custom branding / white-labeling beyond domain configuration
- Self-hosted Stripe alternatives (e.g., embedded billing without Stripe)
