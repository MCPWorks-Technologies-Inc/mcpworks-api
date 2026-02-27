# Tasks: OAuth Social Login & Transactional Email System

**Input**: Design documents from `/specs/002-oauth-email-system/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/oauth-endpoints.yaml, quickstart.md

**Tests**: Not included (not explicitly requested in specification). Add test tasks if TDD approach is desired.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add new dependency, extend configuration, prepare environment

- [x] T001 Add `authlib>=1.3.0` to requirements.txt
- [x] T002 Add OAuth provider settings (Google, GitHub, Microsoft client ID/secret) and Resend settings (API key, from email) to `src/mcpworks_api/config.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database models, migrations, and shared adapters that ALL user stories depend on

### Models & Exports

- [x] T003 Extend UserStatus enum with `PENDING_APPROVAL` and `REJECTED`, make `password_hash` nullable, add `rejection_reason` column in `src/mcpworks_api/models/user.py`
- [x] T004 [P] Create OAuthAccount model with unique constraints (provider+provider_user_id, user_id+provider) and User relationship in `src/mcpworks_api/models/oauth_account.py`
- [x] T005 [P] Create EmailLog model with indexes (email_type+created_at, recipient+created_at) in `src/mcpworks_api/models/email_log.py`
- [x] T006 Export OAuthAccount and EmailLog from `src/mcpworks_api/models/__init__.py`

### Migrations

- [x] T007 [P] Create migration for user model changes (nullable password_hash, rejection_reason column) in `alembic/versions/20260225_000001_oauth_user_status_changes.py`
- [x] T008 [P] Create migration for oauth_accounts table with unique constraints and indexes in `alembic/versions/20260225_000002_create_oauth_accounts.py`
- [x] T009 [P] Create migration for email_logs table with composite indexes in `alembic/versions/20260225_000003_create_email_logs.py`

### Shared Infrastructure

- [x] T010 Create RedisOAuthCache adapter (get/set/delete async methods, 600s TTL) in `src/mcpworks_api/core/oauth_cache.py`
- [x] T011 Add `require_active_status` dependency following `require_admin()` pattern in `src/mcpworks_api/dependencies.py`
- [x] T012 Initialize Authlib OAuth registry with Google (OIDC+PKCE), GitHub (OAuth 2.0), Microsoft (OIDC+PKCE, common tenant) in `src/mcpworks_api/main.py`

**Checkpoint**: Foundation ready — all models, migrations, and shared infrastructure in place. User story implementation can now begin.

---

## Phase 3: User Story 1 — Sign In with Google (Priority: P1)

**Goal**: Users can click "Sign in with Google", complete OAuth consent, and receive a JWT. New accounts are created automatically as active. Existing accounts are linked by email match.

**Independent Test**: Initiate Google OAuth flow, complete consent, verify JWT is returned with correct user identity. Verify new user created as active. Verify existing user linked without duplicate.

### Implementation for User Story 1

- [x] T013 [US1] Create OAuth service with `get_or_create_user_from_oauth()` logic — match by provider_user_id first, then by email, then create new user. Single DB transaction for account + oauth_account creation. In `src/mcpworks_api/services/oauth.py`
- [x] T014 [US1] Create OAuth router with `GET /v1/auth/oauth/{provider}/login` (redirect to consent screen) and `GET /v1/auth/oauth/{provider}/callback` (exchange code, create/link user, issue JWT) in `src/mcpworks_api/api/v1/oauth.py`
- [x] T015 [US1] Register OAuth router in `src/mcpworks_api/main.py`
- [x] T016 [US1] Add Google OAuth button to `src/mcpworks_api/static/onboarding.html`
- [x] T017 [US1] Add audit logging for OAuth login events (new account created, existing account linked, login via OAuth) using existing `fire_security_event()` pattern in `src/mcpworks_api/services/oauth.py`

**Checkpoint**: Google OAuth sign-in works end-to-end. Users can sign in with Google and receive a JWT.

---

## Phase 4: User Story 2 — Sign In with GitHub and Microsoft (Priority: P1)

**Goal**: Users can also sign in with GitHub or Microsoft. All three providers use the same flow. Users can link multiple providers to one account.

**Independent Test**: Complete OAuth flows with GitHub and Microsoft test accounts. Verify JWT and account linking behave identically to Google. Verify a user can have all three providers linked.

**Depends on**: US1 (OAuth service and router infrastructure)

### Implementation for User Story 2

- [x] T018 [US2] Add GitHub email workaround — call `/user/emails` endpoint when `/user` returns null email. Add `user:email` scope to GitHub OAuth config in `src/mcpworks_api/services/oauth.py`
- [x] T019 [US2] Add Microsoft common tenant handling — skip issuer validation in ID token parsing (`claims_options={"iss": {"essential": True, "values": None}}`) in `src/mcpworks_api/services/oauth.py`
- [x] T020 [US2] Verify GitHub and Microsoft paths work in OAuth router callback handler (provider-specific token exchange and user info extraction) in `src/mcpworks_api/api/v1/oauth.py`
- [x] T021 [US2] Add GitHub and Microsoft OAuth buttons to `src/mcpworks_api/static/onboarding.html`

**Checkpoint**: All three OAuth providers work. Users can sign in with Google, GitHub, or Microsoft and link multiple providers.

---

## Phase 5: User Story 3 — Admin-Approved Email/Password Registration (Priority: P2)

**Goal**: New email/password registrations enter "pending_approval" status. Users cannot log in or access protected resources until an admin approves them. Status-specific error messages are returned for pending and rejected users.

**Independent Test**: Register with email/password, verify account is pending. Attempt login, verify specific error message. Approve via admin endpoint, verify login works.

### Implementation for User Story 3

- [x] T022 [US3] Modify `register_user()` in `src/mcpworks_api/services/auth.py` to set `status="pending_approval"` for email/password registrations and return confirmation response without JWT
- [x] T023 [US3] Add status-specific error messages in `login_user()` in `src/mcpworks_api/services/auth.py` — "pending_approval" returns "Account awaiting admin approval", "rejected" returns "Account not approved"
- [x] T024 [US3] Update registration endpoint response in `src/mcpworks_api/api/v1/auth.py` to return pending status message instead of JWT for email/password registrations
- [x] T025 [US3] Apply `require_active_status` dependency to all protected endpoints in `src/mcpworks_api/api/v1/` routers

**Checkpoint**: Email/password registration creates pending accounts. Login returns status-specific errors. Protected endpoints reject non-active users.

---

## Phase 6: User Story 5 — Admin Dashboard: Pending Approvals (Priority: P2)

**Goal**: Admin dashboard shows pending accounts. Admin can approve or reject with optional reason. Dashboard updates after each action.

**Independent Test**: Create pending accounts, load admin dashboard, verify they appear. Approve one, reject one, verify status changes and dashboard updates.

**Depends on**: US3 (pending_approval status must exist)

### Implementation for User Story 5

- [x] T026 [US5] Add `GET /v1/admin/pending-approvals` endpoint returning list of pending users in `src/mcpworks_api/api/v1/admin.py`
- [x] T027 [US5] Add `POST /v1/admin/users/{user_id}/approve` endpoint — transition pending_approval to active in `src/mcpworks_api/api/v1/admin.py`
- [x] T028 [US5] Add `POST /v1/admin/users/{user_id}/reject` endpoint — transition pending_approval to rejected with optional reason in `src/mcpworks_api/api/v1/admin.py`
- [x] T029 [US5] Add audit logging for admin approve/reject actions using existing security event pipeline in `src/mcpworks_api/api/v1/admin.py`
- [x] T030 [US5] Add "Pending Approvals" section to `src/mcpworks_api/static/admin.html` with user list, approve/reject buttons, and rejection reason input

**Checkpoint**: Admin can view, approve, and reject pending accounts from the dashboard.

---

## Phase 7: User Story 4 — Transactional Email Delivery (Priority: P3)

**Goal**: Platform sends branded emails for key events: welcome (OAuth signup), registration pending (to user), new registration alert (to admin), account approved/rejected (to user). All emails are logged. Emails never block primary requests.

**Independent Test**: Trigger each email type, verify delivery, content accuracy, and audit log entries. Verify primary requests complete even if email fails.

### Implementation for User Story 4

- [x] T031 [US4] Create EmailProvider protocol and ResendProvider (direct httpx POST to `https://api.resend.com/emails`) with retry logic (3 attempts, exponential backoff) in `src/mcpworks_api/services/email.py`
- [x] T032 [US4] Create base HTML email template with mcpworks branding in `src/mcpworks_api/templates/emails/base.html`
- [x] T033 [P] [US4] Create welcome email template in `src/mcpworks_api/templates/emails/welcome.html`
- [x] T034 [P] [US4] Create registration_pending email template in `src/mcpworks_api/templates/emails/registration_pending.html`
- [x] T035 [P] [US4] Create admin_new_registration email template in `src/mcpworks_api/templates/emails/admin_new_registration.html`
- [x] T036 [P] [US4] Create account_approved email template in `src/mcpworks_api/templates/emails/account_approved.html`
- [x] T037 [P] [US4] Create account_rejected email template in `src/mcpworks_api/templates/emails/account_rejected.html`
- [x] T038 [US4] Wire fire-and-forget email dispatch into OAuth signup flow (welcome email) via `asyncio.create_task()` in `src/mcpworks_api/services/oauth.py`
- [x] T039 [US4] Wire email dispatch into registration flow — pending confirmation to user + admin notification in `src/mcpworks_api/services/auth.py`
- [x] T040 [US4] Wire email dispatch into approve/reject flow — user notification in `src/mcpworks_api/api/v1/admin.py`
- [x] T041 [US4] Add email audit logging — create EmailLog record for every send attempt (sent/failed/retrying) in `src/mcpworks_api/services/email.py`

**Checkpoint**: All 5 email types send correctly, retry on failure, and create audit log entries. Primary requests are never blocked by email.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Production readiness, deployment configuration, final validation

- [x] T042 Add OAuth + Resend environment variables to `docker-compose.prod.yml`
- [x] T043 [P] Add rate limiting to OAuth endpoints using existing rate limiting infrastructure in `src/mcpworks_api/api/v1/oauth.py`
- [x] T044 [P] Verify all FR-021 through FR-024 security requirements — audit log entries for all auth events, CSRF state validation, callback URL validation
- [x] T045 Run quickstart.md validation — verify all prerequisites, env vars, migrations, and verification steps work end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1: Google OAuth (Phase 3)**: Depends on Phase 2 — first MVP increment
- **US2: GitHub & Microsoft (Phase 4)**: Depends on US1 (shared OAuth infrastructure)
- **US3: Admin-Approved Registration (Phase 5)**: Depends on Phase 2 — can run in parallel with US1/US2
- **US5: Admin Dashboard (Phase 6)**: Depends on US3 (needs pending_approval status and admin endpoints)
- **US4: Transactional Email (Phase 7)**: Depends on Phase 2 — can start after foundational but benefits from US1/US3/US5 being complete (to wire in dispatchers)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

```
Phase 1 (Setup)
  └─→ Phase 2 (Foundational)
        ├─→ Phase 3 (US1: Google OAuth) ──→ Phase 4 (US2: GitHub + Microsoft)
        ├─→ Phase 5 (US3: Admin Registration) ──→ Phase 6 (US5: Admin Dashboard)
        └─→ Phase 7 (US4: Email) — can start early, but wire-in tasks depend on US1/US3/US5
              └─→ Phase 8 (Polish)
```

### Within Each User Story

- Models before services
- Services before endpoints/routers
- Core implementation before integration points
- Audit logging as final step within story

### Parallel Opportunities

- T004 + T005: OAuthAccount and EmailLog models (different files)
- T007 + T008 + T009: All three migrations (independent schema changes)
- T010 + T011: RedisOAuthCache and require_active_status (different files)
- T033 + T034 + T035 + T036 + T037: All email templates (independent files)
- T043 + T044: Rate limiting and security validation (independent concerns)
- US1/US2 can run in parallel with US3 (independent flows, same foundational phase)

---

## Parallel Example: User Story 4 (Email Templates)

```bash
# Launch all email templates in parallel (different files, no dependencies):
Task: T033 "Create welcome email template in src/mcpworks_api/templates/emails/welcome.html"
Task: T034 "Create registration_pending email template in src/mcpworks_api/templates/emails/registration_pending.html"
Task: T035 "Create admin_new_registration email template in src/mcpworks_api/templates/emails/admin_new_registration.html"
Task: T036 "Create account_approved email template in src/mcpworks_api/templates/emails/account_approved.html"
Task: T037 "Create account_rejected email template in src/mcpworks_api/templates/emails/account_rejected.html"
```

---

## Implementation Strategy

### MVP First (US1: Google OAuth Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T012)
3. Complete Phase 3: User Story 1 — Google OAuth (T013-T017)
4. **STOP and VALIDATE**: Test Google sign-in end-to-end
5. Deploy if ready — users can immediately sign in with Google

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. **US1: Google OAuth** → Test → Deploy (MVP!)
3. **US2: GitHub + Microsoft** → Test → Deploy (all OAuth providers live)
4. **US3: Admin Registration** → Test → Deploy (email/password registrations gated)
5. **US5: Admin Dashboard** → Test → Deploy (admin can manage approvals)
6. **US4: Transactional Email** → Test → Deploy (branded emails for all events)
7. Polish → Final validation → Production release

### Suggested MVP Scope

**Phase 1 + Phase 2 + Phase 3 (US1)** = 17 tasks. Delivers Google OAuth sign-in as a working, deployable feature.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in same phase
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Email templates use simple HTML with inline CSS per spec assumptions
- Fire-and-forget email pattern matches existing `fire_security_event()` pattern
- All OAuth state stored in Redis (not cookies) per R-002 decision
