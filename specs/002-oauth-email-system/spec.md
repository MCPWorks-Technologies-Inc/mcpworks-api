# Feature Specification: OAuth Social Login & Transactional Email System

**Feature Branch**: `002-oauth-email-system`
**Created**: 2026-02-25
**Status**: Draft
**Input**: User description: "Add OAuth 2.0 social login (Google, GitHub, Microsoft), admin-approved email/password registration, and a transactional email system for customer communications."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign In with Google (Priority: P1)

A user visits the mcpworks login page and clicks "Sign in with Google." They are redirected to Google's consent screen, authorize the application, and are redirected back. If they have never used mcpworks before, a new account is created automatically and they are immediately active. If they already have an account with the same email, the Google identity is linked to their existing account. In both cases, they receive a JWT and can begin using the platform.

**Why this priority**: OAuth login is the core feature request. Google has the widest consumer adoption and is the most common social login provider. Delivering this first proves the entire OAuth flow end-to-end.

**Independent Test**: Can be fully tested by initiating a Google OAuth flow and verifying a JWT is returned with correct user identity. Delivers immediate value as a standalone login method.

**Acceptance Scenarios**:

1. **Given** a new user with no mcpworks account, **When** they complete Google OAuth, **Then** a new active account is created with their Google email and name, an OAuth identity is linked, and a JWT is returned.
2. **Given** an existing user whose account email matches the Google email, **When** they complete Google OAuth, **Then** the Google identity is linked to their existing account, and a JWT is returned.
3. **Given** a user who already has Google linked, **When** they sign in with Google again, **Then** they receive a JWT for their existing account without creating duplicates.
4. **Given** a user who denies consent on Google's screen, **When** the callback is received, **Then** the system displays an appropriate error and does not create an account.

---

### User Story 2 - Sign In with GitHub and Microsoft (Priority: P1)

A user signs in using their GitHub or Microsoft account. The flow is identical to Google: redirect, consent, callback, account creation or linking, JWT issued. Users can link multiple providers to the same account.

**Why this priority**: Same priority as Google because all three providers share the same architecture. Implementing one means the other two are incremental.

**Independent Test**: Can be tested by completing OAuth flows with GitHub and Microsoft test accounts and verifying JWTs and account linking behave identically to Google.

**Acceptance Scenarios**:

1. **Given** a user with an existing account (created via Google or email), **When** they sign in with GitHub using the same email, **Then** the GitHub identity is linked to their existing account.
2. **Given** a user with Google and GitHub linked, **When** they sign in with Microsoft (same email), **Then** the Microsoft identity is linked, giving them three login methods.
3. **Given** a user signs in with GitHub using a different email than their existing account, **When** the callback is received, **Then** a new separate account is created (no automatic cross-email linking).

---

### User Story 3 - Admin-Approved Email/Password Registration (Priority: P2)

A new user registers with email and password. Instead of being immediately active, their account enters a "pending approval" status. The admin receives an email notification about the new registration. The admin reviews the pending account in the admin dashboard and approves or rejects it. The user receives an email notification with the decision. If approved, they can now log in normally.

**Why this priority**: This is a modification to the existing registration flow rather than new infrastructure. It depends on the email system (P3) being in place for notifications, but the status gating can be implemented independently.

**Independent Test**: Can be tested by registering a new email/password account, verifying it cannot access protected resources, then approving it via admin endpoint and verifying access is granted.

**Acceptance Scenarios**:

1. **Given** a new user registers with email and password, **When** registration completes, **Then** their account status is "pending_approval" and they receive a confirmation that their account is awaiting review.
2. **Given** a pending account exists, **When** the admin approves it from the dashboard, **Then** the account status changes to "active" and the user is notified by email.
3. **Given** a pending account exists, **When** the admin rejects it, **Then** the account status changes to "rejected" and the user is notified by email with the reason.
4. **Given** a user with "pending_approval" status, **When** they attempt to log in, **Then** they receive an error indicating their account is awaiting approval (not a generic "invalid credentials" message).
5. **Given** a user with "rejected" status, **When** they attempt to log in, **Then** they receive an error indicating their account was not approved.

---

### User Story 4 - Transactional Email Delivery (Priority: P3)

The platform sends timely, branded emails for key account events: welcome messages after OAuth signup, admin approval notifications, account approved/rejected notifications, and security alerts for new logins. All outbound emails are logged for audit purposes.

**Why this priority**: Email is infrastructure that supports the other features. OAuth works without email (users get JWTs directly), and admin approval can work with dashboard-only review. But email is essential for a production-quality experience and must be in place before launch.

**Independent Test**: Can be tested by triggering each email type and verifying delivery, content accuracy, and audit log entries.

**Acceptance Scenarios**:

1. **Given** a new user signs up via OAuth, **When** their account is created, **Then** they receive a welcome email within 60 seconds.
2. **Given** a new email/password registration occurs, **When** the account enters pending status, **Then** the admin receives a notification email with the user's details.
3. **Given** an admin approves a pending account, **When** the approval is saved, **Then** the user receives an approval email within 60 seconds.
4. **Given** any outbound email is sent, **When** delivery completes (or fails), **Then** an audit record is created with recipient, email type, status, and timestamp.
5. **Given** the email provider is unavailable, **When** an email send fails, **Then** the system retries up to 3 times with exponential backoff and logs the failure.

---

### User Story 5 - Admin Dashboard: Pending Approvals (Priority: P2)

An admin visits the admin dashboard and sees a list of accounts pending approval. They can view the user's email, name, and registration date. They can approve or reject each account with an optional reason. The dashboard updates in real-time after each action.

**Why this priority**: The admin needs a way to act on pending registrations. This extends the existing admin dashboard.

**Independent Test**: Can be tested by creating pending accounts and verifying the admin dashboard lists them, and that approve/reject actions update the account status.

**Acceptance Scenarios**:

1. **Given** there are 3 pending accounts, **When** the admin loads the dashboard, **Then** all 3 appear in a "Pending Approvals" section with email, name, and registration date.
2. **Given** an admin approves an account, **When** the action completes, **Then** the account disappears from the pending list and the user count updates.
3. **Given** an admin rejects an account with reason "Unrecognized email domain", **When** the action completes, **Then** the rejection reason is stored and included in the notification email.

---

### Edge Cases

- What happens when a user's OAuth provider email changes after account creation? The linked identity uses provider_user_id (immutable), not email, so login continues to work. Email on the local account is not automatically updated.
- What happens when two different OAuth providers return different emails for the same person? Two separate accounts are created. Users can manually link accounts from their profile in a future release.
- What happens when an OAuth provider is temporarily down? The redirect fails at the provider level. The user sees an error and can retry or use a different provider.
- What happens when a pending user's email matches a later OAuth login? The OAuth login creates a new active account. The pending email/password account remains pending and can be cleaned up by admin.
- What happens when the email provider is completely unavailable for an extended period? Core functionality (OAuth login, admin approval) continues to work. Emails queue for retry. Admin can see approval status in the dashboard regardless of email delivery.
- What happens to the 12 existing users? All existing accounts remain active and unaffected. They can link OAuth providers to their existing accounts by signing in with a provider that matches their email.

## Requirements *(mandatory)*

### Functional Requirements

**OAuth Integration**

- **FR-001**: System MUST support OAuth 2.0 / OpenID Connect login via Google, GitHub, and Microsoft.
- **FR-002**: System MUST redirect users to the chosen provider's consent screen and handle the callback.
- **FR-003**: System MUST issue its own JWT (same format as email/password login) after successful OAuth callback.
- **FR-004**: System MUST create a new account automatically when an OAuth user has no existing account, with status "active" (bypassing admin approval).
- **FR-005**: System MUST link an OAuth identity to an existing account when the provider email matches an existing user's email.
- **FR-006**: System MUST allow a single user to link multiple OAuth providers (Google + GitHub + Microsoft).
- **FR-007**: System MUST store OAuth identity as a separate entity linked to the user (provider name, provider user ID, provider email).
- **FR-008**: System MUST NOT store OAuth access/refresh tokens from providers (only the identity mapping is needed).

**Admin-Approved Registration**

- **FR-009**: System MUST set new email/password registrations to "pending_approval" status instead of "active."
- **FR-010**: System MUST prevent users with "pending_approval" or "rejected" status from accessing protected resources.
- **FR-011**: System MUST return a specific, non-generic error message when a pending or rejected user attempts to log in.
- **FR-012**: System MUST provide admin endpoints to list pending accounts, approve accounts, and reject accounts (with optional reason).
- **FR-013**: System MUST transition account status from "pending_approval" to "active" on admin approval.
- **FR-014**: System MUST transition account status from "pending_approval" to "rejected" on admin rejection, storing the reason.

**Transactional Email**

- **FR-015**: System MUST send outbound emails for: welcome (OAuth signup), registration pending (to user), new registration alert (to admin), account approved (to user), account rejected (to user).
- **FR-016**: System MUST use a consistent branded template for all outbound emails.
- **FR-017**: System MUST log every outbound email attempt with recipient, type, status (sent/failed), and timestamp.
- **FR-018**: System MUST retry failed email sends up to 3 times with exponential backoff.
- **FR-019**: System MUST NOT block the primary request (OAuth callback, registration, approval) while sending email. Email delivery MUST be asynchronous.
- **FR-020**: System MUST support a pluggable email provider so the underlying service can be changed without modifying business logic. The initial integration MUST use Resend (3,000 emails/month free tier, simple REST API, 40MB attachment support). The provider abstraction MUST allow swapping to an alternative (e.g., Postmark, SendGrid) via configuration change only.

**Security & Audit**

- **FR-021**: System MUST log all OAuth login events, registration events, and admin approval/rejection events to the existing audit log.
- **FR-022**: System MUST fire security events for new OAuth logins (new provider linked, login from new provider).
- **FR-023**: System MUST validate the OAuth state parameter to prevent CSRF attacks on the callback endpoint.
- **FR-024**: System MUST validate that the OAuth callback comes from a legitimate redirect (registered callback URL only).

### Key Entities

- **User**: Extended with nullable password (OAuth-only users) and new status values (pending_approval, rejected). Represents an authenticated person on the platform.
- **OAuth Account**: Links a user to an external identity provider. Key attributes: provider name, provider's user ID, provider email, linked user. A user can have zero or many OAuth accounts.
- **Email Log**: Records every outbound email. Key attributes: recipient, email type, delivery status, send timestamp, retry count. Used for audit and debugging.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete OAuth sign-in (from clicking provider button to receiving a JWT) in under 10 seconds, excluding time spent on the provider's consent screen.
- **SC-002**: 100% of new email/password registrations enter pending state and cannot access protected resources until admin-approved.
- **SC-003**: Admins are notified of new pending registrations within 2 minutes of submission.
- **SC-004**: 95% of transactional emails are delivered within 60 seconds of the triggering event.
- **SC-005**: All existing users retain full access with no disruption during and after the rollout.
- **SC-006**: Users can link all three OAuth providers to a single account and sign in with any of them.
- **SC-007**: Every outbound email and authentication event has a corresponding audit log entry with zero gaps.
- **SC-008**: The email provider can be swapped without changing any business logic or user-facing behavior.

## Assumptions

- OAuth provider developer accounts (Google Cloud Console, GitHub Developer Settings, Azure AD) will be created and configured by the project owner before implementation begins.
- The existing admin dashboard at `/admin` will be extended (not replaced) to support pending approvals.
- Email templates will use simple HTML with inline CSS (no complex templating engine) for maximum email client compatibility.
- The platform's domain `mcpworks.io` will be verified with the chosen email provider for deliverability (SPF, DKIM, DMARC).
- OAuth callback URLs will use `https://api.mcpworks.io/v1/auth/oauth/{provider}/callback` as the registered redirect URI with each provider.
- The "pending_approval" requirement applies only to new email/password registrations going forward; existing active accounts are not affected.
- Rate limiting on OAuth endpoints will use the same infrastructure as existing auth rate limiting.
