# Tasks: Open-Source Self-Hosting Readiness

**Input**: Design documents from `/specs/005-oss-self-hosting/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-changes.md, quickstart.md

**Tests**: Included — spec requests unit tests for url_builder, SMTP provider, billing bypass, and registration gate.

**Organization**: Tasks grouped by user story. US1 (Domain-Agnostic Deployment) is the foundation and MVP.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Add new configuration settings and create the URL builder utility that all user stories depend on.

- [x] T001 Add `base_domain`, `base_scheme`, `allow_registration`, and SMTP settings to Settings class in src/mcpworks_api/config.py
- [x] T002 Create centralized URL builder module with `create_url()`, `run_url()`, `agent_url()`, `mcp_url()`, `api_url()`, `view_url()`, `chat_url()`, `valid_suffixes()` functions in src/mcpworks_api/url_builder.py
- [x] T003 Write unit tests for url_builder verifying all URL functions with default domain, custom domain, custom scheme, and port-in-domain in tests/unit/test_url_builder.py

**Checkpoint**: URL builder and config ready — all user story work can begin.

---

## Phase 2: User Story 1 - Domain-Agnostic Deployment (Priority: P1) 🎯 MVP

**Goal**: All generated URLs, subdomain routing, admin access, and email links use `BASE_DOMAIN` instead of hardcoded mcpworks.io.

**Independent Test**: Deploy with `BASE_DOMAIN=selfhost.dev` and verify all URLs use that domain. Deploy without `BASE_DOMAIN` and verify backward compat with mcpworks.io.

### Implementation for User Story 1

- [x] T004 [US1] Update SubdomainMiddleware to use `settings.base_domain` for DEFAULT_DOMAIN and rebuild SUBDOMAIN_PATTERN regex dynamically in src/mcpworks_api/middleware/subdomain.py
- [x] T005 [US1] Update `_admin_domains` to derive from `settings.base_domain` instead of hardcoded set in src/mcpworks_api/main.py
- [x] T006 [US1] Replace hardcoded namespace URL properties with url_builder calls in src/mcpworks_api/models/namespace.py
- [x] T007 [P] [US1] Replace hardcoded `run_url` fallback with `url_builder.run_url()` in src/mcpworks_api/mcp/code_mode.py
- [x] T008 [P] [US1] Replace hardcoded `run_url` fallback with `url_builder.run_url()` in src/mcpworks_api/mcp/code_mode_ts.py
- [x] T009 [US1] Replace hardcoded run and agent URLs (2 locations) with url_builder calls in src/mcpworks_api/mcp/run_handler.py
- [x] T010 [US1] Replace hardcoded agent view/chat URLs (2 locations) with url_builder calls in src/mcpworks_api/mcp/create_handler.py
- [x] T011 [P] [US1] Replace hardcoded chat URL with `url_builder.chat_url()` in src/mcpworks_api/services/agent_service.py
- [x] T012 [P] [US1] Replace hardcoded view URL with `url_builder.view_url()` in src/mcpworks_api/services/scratchpad.py
- [x] T013 [US1] Replace hardcoded valid_suffixes list with `url_builder.valid_suffixes()` in src/mcpworks_api/api/v1/health.py
- [x] T014 [P] [US1] Replace hardcoded endpoint examples with url_builder calls in src/mcpworks_api/api/v1/llm.py
- [x] T015 [P] [US1] Replace hardcoded agent domain check with url_builder in src/mcpworks_api/api/v1/scratchpad_view.py
- [x] T016 [P] [US1] Replace hardcoded agent domain patterns with url_builder in src/mcpworks_api/api/v1/public_chat.py
- [x] T017 [P] [US1] Replace hardcoded agent domain patterns with url_builder in src/mcpworks_api/api/v1/webhooks.py
- [x] T018 [US1] Inject `base_url` (derived from `BASE_DOMAIN`) into Jinja2 email template globals in src/mcpworks_api/services/email.py
- [x] T019 [US1] Update base email template to use `{{ base_url }}` for all hyperlinks in src/mcpworks_api/templates/emails/base.html
- [x] T020 [US1] Update JWT issuer/audience defaults to derive from `base_domain` when not explicitly overridden in src/mcpworks_api/config.py
- [x] T021 [US1] Update CORS origins defaults to include `base_domain` subdomains in src/mcpworks_api/config.py
- [x] T022 [US1] Run `grep -r "mcpworks\.io" src/ --include="*.py"` and verify zero hardcoded runtime references remain (defaults with override are OK)

**Checkpoint**: US1 complete — all generated URLs use BASE_DOMAIN. Backward compatible when unset.

---

## Phase 3: User Story 5 - License and Legal Clarity (Priority: P1)

**Goal**: BSL 1.1 LICENSE file exists at repo root with correct parameters. README references it.

**Independent Test**: Verify LICENSE file exists and contains BSL 1.1 text with MCPWorks Inc. licensor, 4-year change date, Apache 2.0 change license.

### Implementation for User Story 5

- [x] T023 [P] [US5] Create LICENSE file with BSL 1.1 text (Licensor: MCPWorks Inc., Change Date: 2030-03-22, Change License: Apache License 2.0) in LICENSE
- [x] T024 [P] [US5] Add license badge and self-hosting section link to README.md

**Checkpoint**: US5 complete — legal clarity established.

---

## Phase 4: User Story 2 - One-Command Self-Hosted Deployment (Priority: P1)

**Goal**: Self-hoster can run `docker compose -f docker-compose.self-hosted.yml up` with bundled postgres, redis, caddy, and API.

**Independent Test**: On a fresh Linux server, clone repo, copy `.env.self-hosted.example` to `.env`, generate keys, run compose, verify health endpoint responds.

### Implementation for User Story 2

- [x] T025 [P] [US2] Create `.env.self-hosted.example` with all required and optional env vars, guided comments, `BASE_DOMAIN=localhost`, `ALLOW_REGISTRATION=false`, no Stripe/Resend keys in .env.self-hosted.example
- [x] T026 [P] [US2] Create Caddyfile template using `{$BASE_DOMAIN}` env var substitution for api, *.create, *.run, *.agent server blocks in Caddyfile.self-hosted
- [x] T027 [US2] Create self-hosted Docker Compose with postgres:15, redis:7-alpine, api (from Dockerfile), and caddy (from Caddyfile.self-hosted) services in docker-compose.self-hosted.yml
- [x] T028 [US2] Create seed script that reads `ADMIN_EMAIL` and `ADMIN_PASSWORD` from env, creates admin user via SQLAlchemy, and prints confirmation in scripts/seed_admin.py
- [x] T029 [US2] Add `allow_registration` gate at top of registration handler — return 403 with `registration_disabled` error when disabled in src/mcpworks_api/api/v1/auth.py
- [x] T030 [US2] Write unit test for registration gate (enabled/disabled) in tests/unit/test_registration_gate.py

**Checkpoint**: US2 complete — single-command self-hosted deployment works.

---

## Phase 5: User Story 3 - Billing-Optional Operation (Priority: P2)

**Goal**: Platform operates without Stripe — no billing checks, no execution limits, self-hosted status in account endpoints.

**Independent Test**: Start without Stripe env vars, register user, create function, execute it — no billing errors.

### Implementation for User Story 3

- [x] T031 [US3] Add `billing_enabled` property to BillingMiddleware (checks `settings.stripe_secret_key` truthiness), add early return in `dispatch()` when disabled in src/mcpworks_api/middleware/billing.py
- [x] T032 [US3] Update account/usage endpoint to return self-hosted status (`tier: "self-hosted"`, `billing_enabled: false`, `executions_limit: -1`) when billing disabled in src/mcpworks_api/api/v1/account.py
- [x] T033 [P] [US3] Update subscriptions endpoint to return 404 with `billing_not_configured` error when Stripe not configured in src/mcpworks_api/api/v1/subscriptions.py
- [x] T034 [US3] Write unit tests for billing bypass (middleware skip, account response, subscriptions 404) in tests/unit/test_billing_bypass.py

**Checkpoint**: US3 complete — Stripe-free operation works.

---

## Phase 6: User Story 6 - Self-Hosting Documentation (Priority: P2)

**Goal**: Step-by-step guide from clone to running MCPWorks instance.

**Independent Test**: Someone unfamiliar with MCPWorks can follow the guide to a working deployment.

### Implementation for User Story 6

- [ ] T035 [US6] Write self-hosting guide covering prerequisites (Linux, Docker, domain, DNS), key generation, env configuration, compose up, seed admin, verification, nsjail vs SANDBOX_DEV_MODE, and troubleshooting in docs/SELF-HOSTING.md

**Checkpoint**: US6 complete — self-hosting is documented.

---

## Phase 7: User Story 4 - Email Provider Flexibility (Priority: P3)

**Goal**: SMTP as alternative to Resend. Silent fail when neither configured.

**Independent Test**: Configure SMTP credentials, trigger welcome email, verify delivery via SMTP.

### Implementation for User Story 4

- [x] T036 [US4] Create SmtpProvider class implementing EmailProvider protocol using aiosmtplib in src/mcpworks_api/services/smtp_provider.py
- [x] T037 [US4] Update `_get_provider()` selection logic: Resend → SMTP → ConsoleProvider in src/mcpworks_api/services/email.py
- [x] T038 [US4] Add `aiosmtplib` to project dependencies in pyproject.toml
- [x] T039 [US4] Write unit tests for SMTP provider and provider selection logic in tests/unit/test_smtp_provider.py

**Checkpoint**: US4 complete — email works via Resend, SMTP, or silent fallback.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and cleanup across all stories.

- [ ] T040 Run full hardcoded domain audit: `grep -r "mcpworks\.io" src/ --include="*.py" | grep -v __pycache__` — verify zero runtime hardcoding remains
- [ ] T041 Run existing test suite (`pytest tests/unit/ --ignore=tests/unit/test_mcp_protocol.py --ignore=tests/unit/test_mcp_router.py -q`) and verify no regressions
- [ ] T042 Verify backward compatibility: start with no `BASE_DOMAIN` set, confirm all URLs default to mcpworks.io
- [ ] T043 Update `.env.example` to document new env vars (BASE_DOMAIN, BASE_SCHEME, ALLOW_REGISTRATION, SMTP_*)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **US1 Domain-Agnostic (Phase 2)**: Depends on Phase 1 (url_builder + config)
- **US5 License (Phase 3)**: No dependencies — can run in parallel with Phase 2
- **US2 Self-Hosted Deploy (Phase 4)**: Depends on Phase 2 (needs domain config working)
- **US3 Billing-Optional (Phase 5)**: Depends on Phase 1 only (config settings)
- **US6 Documentation (Phase 6)**: Depends on Phases 2-5 (documents what was built)
- **US4 Email Flexibility (Phase 7)**: Depends on Phase 1 only (config settings)
- **Polish (Phase 8)**: Depends on all user stories

### User Story Dependencies

- **US1 (P1)**: Foundation — most other stories depend on this
- **US5 (P1)**: Independent — no code dependencies, can run anytime
- **US2 (P1)**: Depends on US1 (compose needs domain config working)
- **US3 (P2)**: Independent of US1 (billing is separate from domain)
- **US6 (P2)**: Depends on US1, US2, US3 (documents the whole setup)
- **US4 (P3)**: Independent of US1 (email is separate from domain)

### Parallel Opportunities

- **Phase 1**: T002 and T003 can parallelize after T001
- **Phase 2**: T007, T008, T011, T012, T014, T015, T016, T017 all modify different files — parallelizable
- **Phase 3**: T023 and T024 are independent — parallelizable
- **Phase 4**: T025 and T026 are independent — parallelizable
- **US3 and US4**: Can run in parallel with each other (different subsystems)
- **US5**: Can run in parallel with everything

---

## Parallel Example: User Story 1

```bash
# After T004-T006 (middleware + main + namespace model), these can all run in parallel:
T007: code_mode.py
T008: code_mode_ts.py
T011: agent_service.py
T012: scratchpad.py
T014: llm.py
T015: scratchpad_view.py
T016: public_chat.py
T017: webhooks.py
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 5)

1. Complete Phase 1: Setup (config + url_builder)
2. Complete Phase 2: US1 Domain-Agnostic Deployment
3. Complete Phase 3: US5 License
4. **STOP and VALIDATE**: Run domain audit, verify backward compat
5. This is a deployable, legally-clear open-source package

### Incremental Delivery

1. Setup + US1 + US5 → Domain-configurable, licensed OSS package (MVP)
2. Add US2 → Self-hosted compose, seed script, Caddyfile
3. Add US3 → Billing-optional mode
4. Add US4 → SMTP email support
5. Add US6 → Complete self-hosting documentation
6. Polish → Final audit, regression check

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Total: 43 tasks across 8 phases
- Tests included for: url_builder (T003), registration gate (T030), billing bypass (T034), SMTP provider (T039)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
