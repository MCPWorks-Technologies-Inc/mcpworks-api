# mcpworks Infrastructure MCP Server - Specification

**Version:** 1.3.0
**Created:** 2025-10-30
**Last Updated:** 2025-10-31
**Status:** Ready for Implementation
**Spec Author:** Simon Carr (CTO)
**Reviewers:** [Codex ultrareview - all critical issues resolved]

---

## 1. Overview

### 1.1 Purpose

The mcpworks Infrastructure MCP Server is a Model Context Protocol implementation that enables AI assistants (Claude Code, Codex, GitHub Copilot, etc.) to directly provision and manage complete web application infrastructure including hosting, domains, SSL certificates, deployment pipelines, and third-party integrations (Stripe, Shopify, SendGrid, Twilio, Zendesk).

### 1.2 User Value

**Problem Solved:** Developers using AI assistants currently face a fragmented experience when deploying applications. They must manually context-switch between multiple platforms (hosting providers, domain registrars, SSL vendors, payment processors) to set up infrastructure. This takes 10-18 hours of manual work across 6+ platforms for a complete application stack.

**Solution:** mcpworks provides a single AI-native interface that reduces complete stack provisioning from 10-18 hours to 8 minutes, with zero manual platform switching. AI assistants make intelligent provisioning decisions based on transparent credit costs, eliminating surprise bills and enabling real-time cost optimization.

**Pain Points Addressed:**
- Eliminates manual context-switching between platforms
- Provides transparent, LLM-accessible pricing for intelligent decisions
- Reduces developer cognitive load during infrastructure setup
- Enables AI to handle full deployment lifecycle (provision → deploy → monitor)
- Offers bank-grade transaction safety (no partial deployments, no double-charging)

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] AI assistant can provision complete application stack (hosting + domain + SSL + payments) in <10 minutes
- [ ] All MCP tool responses average <500 tokens (token efficiency target)
- [ ] Long-running operations (deployments) stream real-time progress via SSE
- [ ] Credit system implements hold/commit/release pattern with zero double-charging bugs
- [ ] Multi-step operations (e.g., e-commerce setup) are fully transactional with automatic rollback
- [ ] Backend infrastructure is provider-agnostic (swappable DigitalOcean → Cloudflare → AWS)
- [ ] Security guardrails prevent port abuse while maintaining AI flexibility
- [ ] 95%+ deployment success rate for standard application types (Node.js, Python, static sites)

### 1.4 Scope

**In Scope:**
- MCP protocol server implementation with 19 tools
- Hosting service provisioning (compute instances, storage; managed databases in Phase 2 per Limitation 3)
- Domain registration and DNS management
- SSL certificate provisioning and renewal automation
- Application deployment from Git repositories with live log streaming
- Third-party SaaS integrations (Stripe, Shopify, SendGrid, Twilio, Zendesk)
- Credit-based billing with transparent LLM-accessible pricing
- Transaction safety with hold/commit/release credit pattern
- Server-Sent Events (SSE) streaming for long-running operations
- Provider abstraction layer for backend-agnostic architecture
- Security guardrails (port restrictions, resource limits, rate limiting)

**Out of Scope:**
- Human-driven web UI (AI-first interface only)
- Custom application code generation (focuses on infrastructure, not code)
- Database query execution or data manipulation (provision only, not operate)
- Email inbox hosting (transactional email sending only via SendGrid/Postmark)
- Direct user support (support services via Zendesk integration)
- Multi-currency billing (CAD only for Phase 1)
- Regulatory compliance for end-user applications (customer responsibility)

---

## 2. User Scenarios

### 2.1 Primary Scenario: Deploy Node.js Application with Complete Stack

**Actor:** AI Assistant (Claude Code)
**Goal:** Deploy user's Node.js application with production infrastructure
**Context:** User has git repository with Node.js app, wants production deployment with custom domain

**Workflow:**
1. User requests: "Deploy my app from https://github.com/user/my-app.git on my domain myapp.com"
2. AI assistant checks credit balance via `get_credit_balance` tool
3. AI assistant provisions hosting via `provision_service` (receives service_id, credit_burn_rate)
4. AI assistant registers domain via `register_domain` (receives domain_id)
5. AI assistant provisions SSL via `provision_ssl` (receives cert_id)
6. AI assistant deploys application via `deploy_application` (receives deployment_id, stream_url)
7. AI assistant subscribes to SSE stream for real-time deployment progress
8. User sees live updates: "Cloning repository... Installing dependencies... Building... Deploying..."
9. Deployment completes: AI assistant receives final status with URL and total credits burned
10. AI assistant confirms to user: "Deployed at https://myapp.com (42 credits burned, 2.5 credits/hour ongoing)"

**Success:** Application is live at custom domain with SSL, user knows exact costs, AI has transaction receipt
**Failure:** Deployment fails at build step → credits held are automatically released, AI receives detailed error, user pays nothing

### 2.2 Secondary Scenario: Launch E-commerce Store (Transactional Multi-Step)

**Actor:** AI Assistant (Codex)
**Goal:** Set up complete online pottery store with Shopify and Stripe
**Context:** User is entrepreneur with no technical background, wants complete e-commerce solution

**Workflow:**
1. User requests: "Create an online store for my pottery business"
2. AI assistant initiates transactional workflow (6 operations with automatic rollback)
3. Operation 1: Provision hosting service (hosting for admin dashboard/landing page)
4. Operation 2: Register domain "artisanpottery.com"
5. Operation 3: Provision SSL certificate for domain
6. Operation 4: Setup Shopify store via `setup_shopify_store`
7. Operation 5: Setup Stripe payment processing via `setup_stripe_account`
8. Operation 6: Connect Stripe to Shopify via `connect_stripe_to_shopify`
9. AI assistant streams progress for each step via SSE
10. User sees live updates: "Provisioning hosting (16%)... Registering domain (33%)... Creating Shopify store (66%)..."
11. All operations complete successfully: credits committed, user receives admin URLs
12. AI assistant confirms: "Your pottery store is live at https://artisan-pottery.myshopify.com (87 credits/month + 2.5 credits/hour hosting)"

**Success:** Complete e-commerce stack operational, user can add products immediately, knows exact monthly costs
**Failure:** Shopify setup fails at Step 4 → automatic rollback tears down SSL (Step 3), domain (Step 2 - credit refund), hosting (Step 1), all credits released, user pays nothing

### 2.3 Tertiary Scenario: Deployment Rollback After Production Issue

**Actor:** AI Assistant (GitHub Copilot)
**Goal:** Rollback broken deployment to previous working version
**Context:** User deployed new version that crashes, needs immediate rollback

**Workflow:**
1. User reports: "App is broken, rollback to previous version"
2. AI assistant queries deployment history via `get_deployment_logs` (identifies last working deployment)
3. AI assistant confirms with user: "Roll back to deployment from 2 hours ago? (Service will restart, ~5 credits cost)"
4. User confirms
5. AI assistant executes `rollback_deployment` (receives rollback_deployment_id, stream_url)
6. AI assistant subscribes to SSE stream for rollback progress
7. System performs zero-downtime rollback: new instances start → health check passes → old instances terminate
8. Rollback completes in <60 seconds
9. AI assistant confirms: "Rolled back to previous version. App is operational. (4.2 credits burned)"

**Success:** Application restored to working state in <60 seconds, minimal downtime, user knows cost
**Failure:** Rollback fails (corrupted previous deployment) → system maintains current deployment, alerts user, AI suggests alternative recovery

---

## 3. Functional Requirements

### 3.1 Core Capabilities

**REQ-MCP-001: MCP Protocol Compliance**
- **Description:** Server MUST implement MCP protocol specification v1.0+ with stdio, SSE, and WebSocket transports
- **Priority:** Must Have
- **Rationale:** Protocol compliance ensures compatibility with all MCP clients (Claude Code, Codex, etc.)
- **Acceptance:** Server passes MCP protocol compliance test suite, successfully integrates with Claude Code and Codex without errors

**REQ-MCP-002: Tool Exposure**
- **Description:** Server MUST expose 19 tools for infrastructure management, deployment, and third-party integrations
- **Priority:** Must Have
- **Rationale:** Complete toolset enables AI to manage full application lifecycle without manual intervention
- **Acceptance:** All 19 tools (provision_service, deploy_application, setup_stripe_account, etc.) are callable via MCP, return valid responses, and handle errors gracefully

**REQ-MCP-003: Resource Exposure**
- **Description:** Server MUST expose 8 resources for credit balance, service inventory, domain portfolio, integration catalog, and deployment history
- **Priority:** Must Have
- **Rationale:** Resources enable AI to make informed decisions based on current account state
- **Acceptance:** All resources are queryable via MCP, return token-efficient responses (<200 tokens), and update in real-time

**REQ-CREDIT-001: Credit System Implementation**
- **Description:** Server MUST implement credit-based billing with 1 credit = $0.01 CAD, minimum 2400 credit purchase, 30-day expiration
- **Priority:** Must Have
- **Rationale:** Transparent pricing enables LLM cost reasoning and prevents surprise bills
- **Acceptance:** Credits purchased are tracked accurately, expiration enforced, burn rates calculated correctly for all service types

**REQ-CREDIT-002: Hold/Commit/Release Pattern**
- **Description:** Server MUST implement three-phase commit for all credit-consuming operations (hold credits → execute operation → commit actual cost OR release on failure)
- **Priority:** Must Have
- **Rationale:** Prevents double-charging, race conditions, and ensures atomic credit operations
- **Acceptance:** Zero double-charging bugs, held credits released on failure, actual costs never exceed estimated costs, concurrent operations handle credit holds correctly

#### Credit Transaction State Machine

**Credit States (account balance):**
1. **AVAILABLE** - Credits in account balance, not allocated to any operation
2. **HELD** - Credits reserved for specific operation, temporarily unavailable
3. **COMMITTED** - Credits permanently deducted for completed operation (terminal state)

**Hold Record States (tracking individual operations):**
1. **held** - Hold is active, credits reserved
2. **committed** - Operation completed, actual cost deducted
3. **released** - Hold cancelled/failed, credits returned to AVAILABLE
4. **expired** - Hold timed out, credits returned to AVAILABLE

**State Transitions:**

```
AVAILABLE --[hold]--> HELD --[commit]--> COMMITTED (terminal state)
                  |
                  +--[release]--> AVAILABLE (hold record: status=released)
                  |
                  +--[expire]--> AVAILABLE (hold record: status=expired, auto-cleanup)
```

**Hold Operation:**
- **Input:**
  - `account_id` (required)
  - `operation_id` (required)
  - `estimated_credits` (required)
  - `max_duration_hours` (optional, default: 4 hours) - Maximum time before automatic expiration
- **Preconditions:**
  - Account balance (AVAILABLE) >= `estimated_credits`
  - No existing hold with same `operation_id` (idempotency check)
  - Account lock acquired (prevents race conditions)
- **Actions:**
  1. Acquire account-level pessimistic lock (row-level DB lock)
  2. Verify sufficient AVAILABLE credits
  3. Create hold record: `{hold_id, operation_id, account_id, amount, created_at, expires_at}`
  4. Decrease AVAILABLE balance by `amount`
  5. Increase HELD balance by `amount`
  6. Release account lock
- **Success Output:** `{hold_id, expires_at, balance_remaining}`
- **Failure Cases:**
  - Insufficient credits → return `insufficient_credits` error, no state change
  - Duplicate `operation_id` → return existing `hold_id` (idempotent)
  - Lock timeout (>5 seconds) → return `lock_timeout` error, retry suggested
- **Expiration:** Hold expires after `max_duration_hours` (default: 4 hours), automatic transition HELD → AVAILABLE

**Commit Operation:**
- **Input:** `hold_id`, `actual_credits_consumed`
- **Preconditions:**
  - Hold exists in HELD state (not expired, not already committed/released)
  - `actual_credits_consumed` <= `held_amount` (never charge more than estimated)
  - Account lock acquired
- **Actions:**
  1. Acquire account-level pessimistic lock
  2. Verify hold exists and is in HELD state
  3. Calculate refund: `refund = held_amount - actual_credits_consumed`
  4. Update hold record: `{status=committed, committed_at=now(), actual_amount=actual_credits_consumed}`
  5. Decrease HELD balance by `held_amount`
  6. Increase COMMITTED balance by `actual_credits_consumed`
  7. Increase AVAILABLE balance by `refund` (if any)
  8. Create billing record: `{account_id, operation_id, amount=actual_credits_consumed, timestamp}`
  9. Release account lock
- **Success Output:** `{committed_amount, refunded_amount, balance_remaining}`
- **Failure Cases:**
  - Hold not found → return `hold_not_found` error (may have expired)
  - Hold already committed with same `actual_credits_consumed` → return original commit result (fully idempotent)
  - Hold already committed with **different** `actual_credits_consumed` → return `conflict_idempotency_violation` error with original committed amount (prevents accidental double-charge corrections)
  - Hold already released → return `already_released` error (cannot commit after release)
  - `actual_credits_consumed` > `held_amount` → return `overcharge_attempt` error, log security event
  - Lock timeout (>5 seconds) → return `lock_timeout` error, retry suggested
- **Idempotency:** Second commit with same `hold_id` and same `actual_credits_consumed` returns original commit result; conflicting amounts are rejected

**Release Operation:**
- **Input:** `hold_id`, `reason` (failure_reason, user_cancelled, operation_cancelled)
- **Preconditions:**
  - Hold exists in HELD state (not expired, not already committed/released)
  - Account lock acquired
- **Actions:**
  1. Acquire account-level pessimistic lock
  2. Verify hold exists and is in HELD state
  3. Update hold record: `{status=released, released_at=now(), release_reason=reason}`
  4. Decrease HELD balance by `held_amount`
  5. Increase AVAILABLE balance by `held_amount`
  6. Release account lock
- **Success Output:** `{released_amount, balance_remaining}`
- **Failure Cases:**
  - Hold not found → return `hold_not_found` error (may have expired)
  - Hold already released with same `reason` → return original release result (fully idempotent)
  - Hold already released with **different** `reason` → return original release result with original reason (first release wins, reason parameter is informational only)
  - Hold already committed → return `already_committed` error (cannot release committed credits)
  - Lock timeout (>5 seconds) → return `lock_timeout` error, retry suggested
- **Idempotency:** Second release with same `hold_id` returns original release result regardless of reason parameter (reason is log-only, not transactional)

**Automatic Expiration (Background Job):**
- **Trigger:** Cron job runs every 5 minutes, scans holds with `expires_at < now()` AND `status=held`
- **Actions:** Execute release operation for each expired hold with `reason=expired`
- **Notification:** Log expiration event, notify account owner if hold was >100 credits

**Concurrent Operation Handling:**

**Scenario 1: Simultaneous hold attempts**
- **Race:** Two operations simultaneously attempt to hold credits
- **Resolution:** Database row-level locks serialize operations
  - Operation 1 acquires lock → holds credits → releases lock → succeeds
  - Operation 2 waits for lock (max 5 seconds) → acquires lock → checks remaining balance → may fail with insufficient_credits if Operation 1 consumed most credits
- **Observability:** Log `lock_wait_time` for monitoring (alert if >2 seconds average)

**Scenario 2: User commit/release racing with expiration job**
- **Race:** User calls commit/release while expiration cron job processes same hold
- **Resolution:** Database locks + state checks guarantee one succeeds
  - If user commit acquires lock first → hold moves to committed state → expiration job sees `status=committed`, skips (not eligible for expiration)
  - If expiration acquires lock first → hold moves to released/expired state → user commit sees `hold_not_found` or `already_released` error
  - First operation to acquire lock wins; second operation gets idempotent error response
- **Observability:** Log concurrent_expiration_attempt when expiration job encounters recently-committed/released holds

**Scenario 3: Multiple client commit/release attempts**
- **Race:** Two API clients both try to commit or release same hold (e.g., deployment service + manual API call)
- **Resolution:** Database state checks enforce single transition
  - First commit/release acquires lock → updates hold status → succeeds
  - Second commit/release acquires lock → sees hold already in terminal state → returns idempotent error (`already_committed` or `already_released`)
  - Idempotency guarantee: repeated calls with same parameters return same result
- **Observability:** Log duplicate_operation_attempt with operation_type, hold_id, requestor

**Consistency Guarantees:**
- **Invariant:** `AVAILABLE + HELD + COMMITTED == total_credits_purchased` (no credits created/destroyed)
- **Verification:** Daily reconciliation job verifies invariant, alerts on mismatch
- **Transaction Isolation:** All credit operations execute within ACID database transactions at `SERIALIZABLE` isolation level
- **Audit Trail:** All state transitions logged with timestamp, operation_id, account_id, before/after balances

**REQ-STREAMING-001: SSE Streaming for Long Operations**
- **Description:** Server MUST stream real-time progress, logs, and credit updates via Server-Sent Events (SSE) for deployments and multi-step workflows
- **Priority:** Must Have
- **Rationale:** Real-time visibility builds trust, enables interruptibility, provides immediate feedback
- **Acceptance:** Deployments stream progress events (cloning, building, deploying), log events (build output), credit_update events (current burn), completed/error events (final status)

**REQ-TX-001: Transactional Multi-Step Operations**
- **Description:** Server MUST support transactional workflows where multiple operations execute atomically with automatic rollback on any failure
- **Priority:** Must Have
- **Rationale:** Complex workflows (e-commerce setup) must be all-or-nothing to prevent partial resource provisioning
- **Acceptance:** Multi-step operations (e.g., e-commerce stack setup) rollback completely on failure, no orphaned resources, all credits released

**REQ-PROVIDER-001: Provider Abstraction**
- **Description:** Server MUST implement provider abstraction layer allowing backend infrastructure to be swappable (DigitalOcean → Cloudflare → AWS → Hetzner)
- **Priority:** Must Have
- **Rationale:** Acquisition flexibility - acquirer can migrate backend without MCP API changes
- **Acceptance:** Provider implementation can be swapped via configuration, MCP API remains unchanged, credit burn rates recalculated based on provider pricing

**REQ-SECURITY-001: Port Restrictions**
- **Description:** Server MUST restrict ports to HTTP (80), HTTPS (443), SSH (22) by default, blocking SMTP (25) and SMB (445) permanently
- **Priority:** Must Have
- **Rationale:** Prevents spam/abuse, protects infrastructure reputation, aligns with industry standards
- **Acceptance:** Provisioned services have firewall rules enforcing port restrictions, AI cannot override without explicit user confirmation

**REQ-SECURITY-002: Credential Management**
- **Description:** Server MUST store all third-party API credentials encrypted at rest, NEVER expose credentials via MCP responses
- **Priority:** Must Have
- **Rationale:** Prevents credential leakage through AI assistant logs or responses
- **Acceptance:** Credentials stored in encrypted vault, MCP responses contain only public metadata (account IDs, dashboard URLs), audit logs do not contain credentials

**REQ-DEPLOY-001: Git Repository Deployment**
- **Description:** Server MUST support deploying applications from Git repositories (GitHub, GitLab, Bitbucket) with automatic dependency installation and build execution
- **Priority:** Must Have
- **Rationale:** Enables AI to deploy applications without manual build steps
- **Acceptance:** Supports Node.js (npm/yarn), Python (pip/poetry), Ruby (bundler), Go (go mod), PHP (composer), static sites (no build), executes build commands, reports errors clearly

**REQ-DEPLOY-002: Zero-Downtime Rollback**
- **Description:** Server MUST support rolling back to previous deployment with zero downtime (start new instances → health check → terminate old instances)
- **Priority:** Should Have
- **Rationale:** Production reliability requires instant recovery from bad deployments
- **Acceptance:** Rollback completes in <60 seconds, health checks verify new instances before terminating old, service remains accessible throughout rollback

**REQ-INTEGRATION-001: Stripe Integration**
- **Description:** Server MUST integrate Stripe Connect API for account creation, product management, subscription setup, and payment processing
- **Priority:** Must Have
- **Rationale:** Payment processing is essential for e-commerce and SaaS applications
- **Acceptance:** Can create Stripe accounts, configure products/prices, generate checkout links, securely store API keys, webhook handling for payment events

**REQ-INTEGRATION-002: Shopify Integration**
- **Description:** Server MUST integrate Shopify Partner API for store creation, theme installation, product management, and payment gateway configuration
- **Priority:** Must Have
- **Rationale:** Enables complete e-commerce stack provisioning for non-technical users
- **Acceptance:** Can create Shopify stores, install themes, add products, connect Stripe payment gateway, return admin and storefront URLs

**REQ-INTEGRATION-003: SendGrid/Twilio/Zendesk Integration**
- **Description:** Server MUST integrate SendGrid (transactional email), Twilio (SMS), and Zendesk (support tickets) APIs for complete SaaS application stack
- **Priority:** Should Have
- **Rationale:** Modern applications require email, SMS, and support infrastructure
- **Acceptance:** Can provision SendGrid accounts with domain verification, Twilio accounts with phone numbers, Zendesk instances with email channels

### 3.2 MCP Tool & Resource Catalog

**This section defines the complete API contract for all 19 MCP tools and 8 resources.**

#### 3.2.1 Infrastructure Provisioning Tools

**Tool 1: `provision_service`**
- **Purpose:** Create new hosting service (compute instance)
- **Parameters:**
  - `service_type` (string, required): Type of service ("web_hosting", "storage"; "database" in Phase 2 per Limitation 3)
  - `resource_spec` (object, required):
    - `cpu_cores` (integer, 1-16)
    - `ram_mb` (integer, 512-65536)
    - `storage_gb` (integer, 10-1000)
    - `region` (string, optional): "tor1", "nyc1", "sfo1", "lon1", "fra1" (defaults to "tor1")
  - `duration_estimate` (string, optional): Estimated usage duration ("24h", "720h") for credit hold calculation
- **Returns** (estimated 120 tokens):
  ```json
  {
    "svc": "svc_abc123",
    "status": "provisioning",
    "burn": 2.5,
    "est_mo": "$54 (1800cr)",
    "eta": "2025-10-30T10:15:00Z",
    "ip": "pending"
  }
  ```
- **Error Codes:** `insufficient_credits`, `invalid_resource_spec`, `provider_unavailable`, `rate_limit_exceeded`

**Tool 2: `get_service_status`**
- **Purpose:** Query service health and metrics
- **Parameters:**
  - `service_id` (string, required): Service identifier
  - `detail_level` (string, optional): "summary" (default), "standard", "detailed"
- **Returns** (60-200 tokens depending on detail_level):
  ```json
  {
    "svc": "svc_abc123",
    "status": "running",
    "uptime": "48h",
    "cr_burned": 120.5,
    "metrics": {
      "cpu_pct": 45,
      "mem_pct": 62,
      "disk_pct": 30,
      "net_in_mbps": 12.5,
      "net_out_mbps": 8.3,
      "req_per_sec": 145
    }
  }
  ```
  - **metrics object schema:**
    - `cpu_pct` (number): CPU utilization percentage (0-100)
    - `mem_pct` (number): Memory utilization percentage (0-100)
    - `disk_pct` (number): Disk utilization percentage (0-100)
    - `net_in_mbps` (number): Network ingress in Mbps (last 5 min average)
    - `net_out_mbps` (number): Network egress in Mbps (last 5 min average)
    - `req_per_sec` (number): HTTP requests per second (last 5 min average, web services only)
  - **detail_level variations:**
    - `summary`: Only status, uptime, cr_burned (no metrics)
    - `standard`: Includes cpu_pct, mem_pct, disk_pct (default)
    - `detailed`: All metrics fields including network and req_per_sec
- **Error Codes:** `service_not_found`, `unauthorized`

**Tool 3: `scale_service`**
- **Purpose:** Modify resource allocation (vertical scaling)
- **Parameters:**
  - `service_id` (string, required)
  - `new_resource_spec` (object, required): Same structure as `provision_service`
- **Returns** (80 tokens):
  ```json
  {
    "svc": "svc_abc123",
    "status": "scaling",
    "burn_old": 2.5,
    "burn_new": 5.0,
    "burn_change": 2.5,
    "est_downtime": "30s"
  }
  ```
  - **burn_change format:** Numeric value (positive for increase, negative for decrease)
    - Example: Scaling from 2.5 → 5.0 credits/hour: `burn_change: 2.5` (increase)
    - Example: Scaling from 5.0 → 2.5 credits/hour: `burn_change: -2.5` (decrease)
    - Calculation: `burn_change = burn_new - burn_old`
- **Error Codes:** `insufficient_credits`, `scaling_not_supported`, `downtime_required`

**Tool 4: `deprovision_service`**
- **Purpose:** Terminate service and release resources
- **Parameters:**
  - `service_id` (string, required)
  - `backup_request` (boolean, optional): Create final backup before termination
- **Returns** (100 tokens):
  ```json
  {
    "svc": "svc_abc123",
    "status": "deprovisioning",
    "cr_final": 156.3,
    "backup_url": "https://backups.multisphere.ca/svc_abc123_final.tar.gz",
    "eta": "2025-10-30T10:20:00Z"
  }
  ```
- **Error Codes:** `service_not_found`, `active_deployments`, `backup_failed`

#### 3.2.2 Application Deployment Tools

**Tool 5: `deploy_application`**
- **Purpose:** Deploy application from Git repository with streaming logs
- **Parameters:**
  - `service_id` (string, required)
  - `git_repo_url` (string, required): GitHub, GitLab, or Bitbucket HTTPS URL
  - `branch` (string, optional): Branch or tag to deploy (default: "main")
  - `environment_vars` (object, optional): Environment variables (encrypted storage)
    - **Structure:** `{"KEY": "value"}` - flat key-value pairs
    - **Constraints:** Max 100 variables, key names 1-64 chars (alphanumeric + underscore), values max 4KB each
    - **Example:** `{"NODE_ENV": "production", "DATABASE_URL": "postgres://...", "API_KEY": "sk_live_..."}`
    - **Security:** Values encrypted at rest, never logged, available to application at runtime
  - `build_command` (string, optional): Custom build command (default: auto-detect)
    - **Max length:** 256 characters
    - **Example:** `"npm run build"` or `"python setup.py install"`
  - `start_command` (string, optional): Custom start command (default: auto-detect)
    - **Max length:** 256 characters
    - **Example:** `"npm start"` or `"python app.py"`
  - `credits_authorized` (number, required): Maximum credits authorized for deployment
- **Returns** (80 tokens):
  ```json
  {
    "dep": "dep_xyz789",
    "status": "deploying",
    "stream": "https://mcp.multisphere.ca/streams/dep_xyz789",
    "est_cr": 50,
    "held": 50
  }
  ```
- **SSE Stream Events** (Content-Type: text/event-stream):
  - **Event: `progress`**
    ```
    event: progress
    data: {"stage":"cloning","pct":15,"msg":"Cloning repository from GitHub"}
    ```
    - `stage` (string): cloning | building | deploying | starting | completed
    - `pct` (number): 0-100 completion percentage
    - `msg` (string): Human-readable progress message
  - **Event: `log`**
    ```
    event: log
    data: {"ts":"2025-10-30T10:01:23Z","level":"info","line":"npm install completed successfully"}
    ```
    - `ts` (ISO 8601 timestamp): Log event time
    - `level` (string): info | warn | error
    - `line` (string): Log output line (max 1KB)
  - **Event: `credit_update`**
    ```
    event: credit_update
    data: {"burned":18.5,"held":50.0,"est_total":45.0}
    ```
    - `burned` (number): Credits consumed so far
    - `held` (number): Total credits held for operation
    - `est_total` (number): Estimated final cost (may decrease as operation progresses)
  - **Event: `completed`**
    ```
    event: completed
    data: {"status":"success","url":"https://myapp.example.com","cr_final":42.3,"cr_refund":7.7,"duration":127}
    ```
    - `status` (string): success
    - `url` (string): Application URL
    - `cr_final` (number): Final credits charged
    - `cr_refund` (number): Credits returned from hold
    - `duration` (number): Total seconds
  - **Event: `error`**
    ```
    event: error
    data: {"code":"build_failed","msg":"npm install failed: ENOTFOUND express","cr_burned":8.2,"cr_released":41.8,"stage":"building"}
    ```
    - `code` (string): Error code
    - `msg` (string): Human-readable error
    - `cr_burned` (number): Credits charged for work before failure
    - `cr_released` (number): Credits returned to account
    - `stage` (string): Stage where error occurred
- **Error Codes:** `insufficient_credits`, `git_clone_failed`, `build_failed`, `service_not_found`

**Tool 6: `get_deployment_logs`**
- **Purpose:** Retrieve deployment logs (historical or streaming)
- **Parameters:**
  - `deployment_id` (string, required)
  - `stream` (boolean, optional): Real-time streaming (default: false)
  - `tail_lines` (integer, optional): Number of recent lines (default: 50, max: 500)
- **Returns** (200-800 tokens depending on tail_lines):
  ```json
  {
    "dep": "dep_xyz789",
    "status": "completed",
    "logs": ["[10:15:00] Cloning repository...", "..."],
    "cr_burned": 42.5,
    "has_more": false
  }
  ```
- **Error Codes:** `deployment_not_found`, `logs_expired` (>30 days old)

**Tool 7: `rollback_deployment`**
- **Purpose:** Rollback to previous deployment (zero-downtime)
- **Parameters:**
  - `service_id` (string, required)
  - `target_deployment_id` (string, optional): Specific deployment to rollback to (default: previous)
- **Returns** (90 tokens):
  ```json
  {
    "dep": "dep_rollback_123",
    "status": "rolling_back",
    "target": "dep_xyz789",
    "stream": "https://mcp.multisphere.ca/streams/dep_rollback_123",
    "est_cr": 5
  }
  ```
- **SSE Stream Events** (Content-Type: text/event-stream):
  - **Event: `progress`**
    ```
    event: progress
    data: {"stage":"switching","pct":50,"msg":"Switching traffic to previous deployment"}
    ```
    - `stage` (string): preparing | switching | health_check | completed
    - `pct` (number): 0-100 completion percentage
    - `msg` (string): Human-readable progress message
  - **Event: `completed`**
    ```
    event: completed
    data: {"status":"success","url":"https://myapp.example.com","rollback_to":"dep_xyz789","cr_final":3.2,"duration":45}
    ```
    - `status` (string): success
    - `url` (string): Application URL (now serving rolled-back version)
    - `rollback_to` (string): Deployment ID that was restored
    - `cr_final` (number): Credits charged for rollback operation
    - `duration` (number): Total seconds
  - **Event: `error`**
    ```
    event: error
    data: {"code":"health_check_failed","msg":"Rolled-back deployment failed health check","cr_burned":2.1,"stage":"health_check"}
    ```
    - `code` (string): Error code
    - `msg` (string): Human-readable error
    - `cr_burned` (number): Credits charged for work before failure
    - `stage` (string): Stage where error occurred
- **Error Codes:** `deployment_not_found`, `artifacts_expired`, `no_previous_deployment`

#### 3.2.3 Domain & SSL Tools

**Tool 8: `register_domain`**
- **Purpose:** Register new domain name
- **Parameters:**
  - `domain_name` (string, required): Domain to register (e.g., "example.com")
  - `registration_years` (integer, optional): 1-10 years (default: 1)
  - `privacy_protection` (boolean, optional): WHOIS privacy (default: true)
- **Returns** (110 tokens):
  ```json
  {
    "dom": "dom_xyz789",
    "domain": "example.com",
    "status": "registering",
    "cr_cost": 1200,
    "expires": "2026-10-30",
    "ns": ["ns1.cloudflare.com", "ns2.cloudflare.com"]
  }
  ```
- **Error Codes:** `domain_unavailable`, `invalid_domain`, `registration_failed`, `insufficient_credits`

**Tool 9: `provision_ssl`**
- **Purpose:** Provision SSL certificate for domain
- **Parameters:**
  - `domain_name` (string, required)
  - `cert_type` (string, optional): "letsencrypt" (default), "sectigo_dv", "sectigo_ov"
  - `service_id` (string, optional): Auto-install on service if provided
- **Returns** (90 tokens):
  ```json
  {
    "cert": "ssl_def456",
    "domain": "example.com",
    "status": "provisioning",
    "cr_cost": 0,
    "valid_until": "2026-01-28",
    "auto_renew": true
  }
  ```
- **Error Codes:** `domain_verification_failed`, `acme_challenge_failed`, `cert_authority_unavailable`

**Tool 10: `get_domain_status`**
- **Purpose:** Query domain and DNS status
- **Parameters:**
  - `domain_name` (string, required)
- **Returns** (100 tokens):
  ```json
  {
    "dom": "dom_xyz789",
    "domain": "example.com",
    "status": "active",
    "ns_propagated": true,
    "ssl": ["ssl_def456"],
    "expires": "2026-10-30"
  }
  ```
- **Error Codes:** `domain_not_found`, `dns_propagation_pending`

#### 3.2.4 Third-Party Integration Tools

**Tool 11: `setup_stripe_account`**
- **Purpose:** Configure Stripe payment processing
- **Parameters:**
  - `business_name` (string, required)
  - `business_type` (string, required): "individual", "company", "non_profit"
  - `country` (string, required): ISO 3166-1 alpha-2 code ("CA", "US", etc.)
  - `currency` (string, required): ISO 4217 code ("CAD", "USD", etc.)
- **Returns** (120 tokens):
  ```json
  {
    "stripe_acct": "acct_abc123",
    "dashboard": "https://dashboard.stripe.com/acct_abc123",
    "api_configured": true,
    "test_mode": true,
    "cr_cost": 0
  }
  ```
- **Error Codes:** `stripe_verification_required`, `unsupported_country`, `api_error`

**Tool 12: `create_stripe_product`**
- **Purpose:** Create product/price in Stripe
- **Parameters:**
  - `stripe_account_id` (string, required)
  - `product_name` (string, required)
  - `price` (number, required): Amount in smallest currency unit (cents)
  - `billing_interval` (string, optional): "month", "year", "one_time" (default)
- **Returns** (110 tokens):
  ```json
  {
    "product": "prod_xyz789",
    "price": "price_def456",
    "checkout": "https://checkout.stripe.com/c/pay/abc123",
    "amount": "$24.00"
  }
  ```
- **Error Codes:** `stripe_account_invalid`, `price_validation_failed`

**Tool 13: `setup_shopify_store`**
- **Purpose:** Provision Shopify e-commerce store
- **Parameters:**
  - `store_name` (string, required): Store subdomain (e.g., "my-store")
  - `plan_tier` (string, required): "basic", "shopify", "advanced"
  - `theme` (string, optional): Theme name (default: "dawn")
  - `initial_products` (array, optional): Product data for bulk import
    - **Structure:** Array of product objects (max 50 products at setup)
    - **Each product:**
      - `title` (string, required): Max 255 chars
      - `description` (string, optional): Max 5000 chars (HTML allowed)
      - `price` (number, required): Decimal, min 0.01
      - `images` (array of URLs, optional): Max 10 URLs per product
      - `variants` (array, optional): Max 100 variants per product, each variant:
        - `option1` (string, required): E.g., "Small", "Red"
        - `option2` (string, optional): E.g., "Cotton"
        - `option3` (string, optional): Third variant dimension
        - `price` (number, optional): Overrides product price for this variant
        - `sku` (string, optional): Stock keeping unit, max 64 chars
        - `inventory_quantity` (integer, optional): Default 0
    - **Example:**
      ```json
      [
        {
          "title": "Handmade Pottery Mug",
          "description": "Beautiful ceramic mug, dishwasher safe",
          "price": 24.99,
          "images": ["https://example.com/mug-front.jpg"],
          "variants": [
            {"option1": "Blue", "sku": "MUG-BLUE", "inventory_quantity": 10},
            {"option1": "Green", "sku": "MUG-GREEN", "inventory_quantity": 5}
          ]
        }
      ]
      ```
- **Returns** (130 tokens):
  ```json
  {
    "shop": "shop_jkl202",
    "store_url": "https://my-store.myshopify.com",
    "admin_url": "https://my-store.myshopify.com/admin",
    "cr_cost": 87,
    "plan": "basic"
  }
  ```
- **Error Codes:** `shopify_partner_auth_failed`, `store_name_unavailable`, `plan_tier_invalid`

**Tool 14: `add_shopify_product`**
- **Purpose:** Add product to Shopify store
- **Parameters:**
  - `shopify_store_id` (string, required)
  - `product_data` (object, required):
    - `title` (string, required): Max 255 chars
    - `description` (string, optional): Max 5000 chars (HTML allowed)
    - `price` (number, required): Decimal, min 0.01
    - `images` (array of URLs, optional): Max 10 URLs
    - `variants` (array, optional): Max 100 variants, same structure as `setup_shopify_store` initial_products variants
- **Returns** (90 tokens):
  ```json
  {
    "product": "prod_shopify_xyz",
    "product_url": "https://my-store.myshopify.com/products/my-product",
    "status": "active"
  }
  ```
- **Error Codes:** `shopify_store_invalid`, `product_validation_failed`

**Tool 15: `connect_stripe_to_shopify`**
- **Purpose:** Link Stripe payment gateway to Shopify store
- **Parameters:**
  - `shopify_store_id` (string, required)
  - `stripe_account_id` (string, required)
- **Returns** (80 tokens):
  ```json
  {
    "integration": "active",
    "test_mode": true,
    "payment_methods": ["card", "google_pay", "apple_pay"]
  }
  ```
- **Error Codes:** `shopify_store_invalid`, `stripe_account_invalid`, `connection_failed`

**Tool 16: `setup_sendgrid_email`**
- **Purpose:** Configure transactional email service
- **Parameters:**
  - `domain_name` (string, required): Domain for sending emails
  - `sender_email` (string, required): From address (e.g., "hello@example.com")
  - `sender_name` (string, required): Display name
- **Returns** (150 tokens):
  ```json
  {
    "sendgrid": "sg_mno303",
    "api_configured": true,
    "dns_records": [
      {"type": "TXT", "host": "_domainkey.example.com", "value": "..."},
      {"type": "CNAME", "host": "em123.example.com", "value": "u123.wl.sendgrid.net"}
    ],
    "cr_cost": 0
  }
  ```
- **Error Codes:** `sendgrid_api_error`, `domain_verification_pending`

**Tool 17: `setup_twilio_sms`**
- **Purpose:** Configure SMS notification service with phone number provisioning
- **Parameters:**
  - `phone_number_country` (string, required): ISO 3166-1 alpha-2 code (e.g., "US", "CA", "GB")
  - `number_type` (string, optional): "local" | "toll_free" | "short_code" (default: "local")
    - **local**: Standard geographic number (+1-416-555-xxxx)
    - **toll_free**: 1-800/888/etc. number (+1-800-555-xxxx)
    - **short_code**: 5-6 digit number for high-volume messaging (requires approval, 2-3 week provisioning)
  - `use_case` (string, required): "transactional", "marketing", "verification"
    - **transactional**: Order confirmations, shipping notifications (requires opt-in)
    - **marketing**: Promotional messages (requires double opt-in + unsubscribe)
    - **verification**: 2FA codes, account verification (no opt-in required)
  - `capabilities` (object, optional): Messaging capabilities
    - `sms` (boolean): Send/receive SMS (default: true)
    - `mms` (boolean): Send/receive MMS (images, video) (default: false)
    - `voice` (boolean): Voice calls (default: false)
  - `webhook_url` (string, optional): HTTPS URL for incoming message/status callbacks
    - **Signature verification**: Twilio signs webhooks with X-Twilio-Signature header
    - **Retry policy**: 8 hours, exponential backoff
  - `messaging_brand` (string, optional): Brand name for A2P 10DLC registration (US only, max 64 chars)
    - **Required for US local numbers** sending >200 messages/day
    - **Approval time**: 2-5 business days
- **Returns** (100 tokens):
  ```json
  {
    "twilio": "tw_pqr404",
    "phone_number": "+14165551234",
    "number_type": "local",
    "messaging_service": "MG123abc",
    "capabilities": {"sms": true, "mms": true, "voice": false},
    "brand_status": "approved",
    "cr_cost": 15
  }
  ```
- **Error Codes:** `twilio_api_error`, `phone_number_unavailable`, `use_case_rejected`, `brand_registration_pending`, `webhook_url_invalid`

**Tool 18: `setup_zendesk_support`**
- **Purpose:** Configure customer support and ticketing system
- **Parameters:**
  - `subdomain` (string, required): Zendesk subdomain (e.g., "mycompany")
  - `support_email` (string, required): Support email address
  - `business_name` (string, required)
  - `plan_tier` (string, required): "suite_team", "suite_growth", "suite_professional"
- **Returns** (130 tokens):
  ```json
  {
    "zendesk": "zd_stu505",
    "support_portal": "https://mycompany.zendesk.com",
    "admin_url": "https://mycompany.zendesk.com/admin",
    "api_configured": true,
    "cr_cost": 49
  }
  ```
- **Error Codes:** `zendesk_api_error`, `subdomain_unavailable`, `plan_tier_invalid`

#### 3.2.5 Account Management Tools

**Tool 19: `get_account_status`**
- **Purpose:** Query account credits, services, and usage
- **Parameters:** None (implicitly uses authenticated account)
- **Returns** (150 tokens):
  ```json
  {
    "account": "acc_xyz123",
    "credits": {
      "avail": 1234.5,
      "held": 100,
      "burn_rate": 12.5,
      "expires": [{"amt": 500, "exp": "2025-11-15"}]
    },
    "services": {"active": 3, "provisioning": 1},
    "deployments": {"active": 2, "this_month": 15}
  }
  ```
- **Error Codes:** `unauthorized`

#### 3.2.6 MCP Resources

**Resources provide read-only access to account state and configuration.**

**Resource 1: `service_catalog`**
- **URI:** `multisphere://catalog/services`
- **Purpose:** Available service types and pricing
- **Content** (200 tokens):
  ```json
  {
    "services": [
      {"type": "web_hosting", "plans": [
        {"name": "basic-1gb", "cpu": 1, "ram": 1024, "storage": 25, "burn": 1.2},
        {"name": "standard-2gb", "cpu": 2, "ram": 2048, "storage": 50, "burn": 2.5}
      ]},
      {"type": "storage", "plans": [
        {"name": "block-50gb", "storage": 50, "burn": 0.5},
        {"name": "block-100gb", "storage": 100, "burn": 1.0}
      ]}
    ]
  }
  ```

**Resource 2: `account_credits`**
- **URI:** `multisphere://account/credits`
- **Purpose:** Current credit balance and burn rates
- **Content** (100 tokens):
  ```json
  {
    "avail": 1234.5,
    "held": 100.0,
    "committed": 8765.5,
    "burn_rate": 12.5,
    "est_days": 82,
    "expires": [
      {"amt": 500, "exp": "2025-11-15"},
      {"amt": 734.5, "exp": "2025-12-01"}
    ]
  }
  ```
  - `avail` (number): Available credits for new operations
  - `held` (number): Credits currently held by in-progress operations
  - `committed` (number): Total credits burned lifetime
  - `burn_rate` (number): Current credits/hour consumption across all services
  - `est_days` (number): Estimated days until balance depleted (avail / (burn_rate * 24))
  - `expires` (array): Credit batches with expiration dates, sorted by soonest expiration

**Resource 3: `service_inventory`**
- **URI:** `multisphere://account/services`
- **Purpose:** All active services for account
- **Content** (300-800 tokens depending on service count):
  ```json
  {
    "services": [
      {
        "id": "svc_abc123",
        "type": "web_hosting",
        "status": "running",
        "spec": {"cpu": 2, "ram": 2048, "storage": 50},
        "burn": 2.5,
        "ip": "192.0.2.45",
        "region": "tor1",
        "created": "2025-10-15T14:30:00Z",
        "uptime_pct": 99.98
      },
      {
        "id": "svc_def456",
        "type": "storage",
        "status": "running",
        "spec": {"storage": 100},
        "burn": 1.0,
        "region": "nyc1",
        "created": "2025-10-20T09:15:00Z"
      }
    ],
    "total": 2,
    "total_burn": 3.5
  }
  ```
  - Each service: `id`, `type`, `status` (running|stopped|provisioning|error), `spec`, `burn` (credits/hour), `ip` (if applicable), `region`, `created`, `uptime_pct` (optional)

**Resource 4: `domain_portfolio`**
- **URI:** `multisphere://account/domains`
- **Purpose:** Registered domains and SSL certificates
- **Content** (200-600 tokens):
  ```json
  {
    "domains": [
      {
        "id": "dom_xyz789",
        "name": "example.com",
        "status": "active",
        "registered": "2025-10-15",
        "expires": "2026-10-15",
        "auto_renew": true,
        "privacy": true,
        "ns": ["ns1.multisphere.ca", "ns2.multisphere.ca"],
        "ssl": {
          "cert_id": "ssl_abc123",
          "type": "letsencrypt",
          "issued": "2025-10-15",
          "expires": "2026-01-15",
          "auto_renew": true
        }
      }
    ],
    "total": 1
  }
  ```
  - Each domain: `id`, `name`, `status` (active|pending|expired), `registered`, `expires`, `auto_renew`, `privacy`, `ns` (nameservers), `ssl` (certificate details)

**Resource 5: `integration_catalog`**
- **URI:** `multisphere://catalog/integrations`
- **Purpose:** Available third-party integrations (Stripe, Shopify, etc.)
- **Content** (250 tokens):
  ```json
  {
    "integrations": [
      {
        "provider": "stripe",
        "name": "Stripe Payments",
        "desc": "Payment processing and subscription management",
        "auth": "api_key",
        "features": ["payments", "subscriptions", "invoices"],
        "credit_cost": 1
      },
      {
        "provider": "shopify",
        "name": "Shopify Store",
        "desc": "E-commerce platform integration",
        "auth": "oauth",
        "features": ["products", "inventory", "orders"],
        "credit_cost": 1
      },
      {
        "provider": "sendgrid",
        "name": "SendGrid Email",
        "desc": "Transactional email delivery",
        "auth": "api_key",
        "features": ["email_send", "templates"],
        "credit_cost": 1
      }
    ]
  }
  ```
  - Each integration: `provider`, `name`, `desc`, `auth` (api_key|oauth), `features`, `credit_cost` (per API call)

**Resource 6: `active_integrations`**
- **URI:** `multisphere://account/integrations`
- **Purpose:** All configured third-party services for account
- **Content** (150-400 tokens):
  ```json
  {
    "integrations": [
      {
        "id": "int_stripe_abc",
        "provider": "stripe",
        "status": "active",
        "connected": "2025-10-16T10:00:00Z",
        "last_used": "2025-10-30T08:15:00Z",
        "api_calls_month": 1247,
        "credits_month": 1247,
        "metadata": {
          "account_name": "Acme Corp",
          "dashboard_url": "https://dashboard.stripe.com"
        }
      },
      {
        "id": "int_shopify_def",
        "provider": "shopify",
        "status": "active",
        "connected": "2025-10-18T14:30:00Z",
        "last_used": "2025-10-29T16:45:00Z",
        "api_calls_month": 542,
        "credits_month": 542,
        "metadata": {
          "store_url": "mystore.myshopify.com",
          "admin_url": "https://mystore.myshopify.com/admin"
        }
      }
    ],
    "total": 2
  }
  ```
  - Each integration: `id`, `provider`, `status` (active|error|pending_auth), `connected`, `last_used`, `api_calls_month`, `credits_month`, `metadata` (provider-specific public info)

**Resource 7: `deployment_history`**
- **URI:** `multisphere://account/deployments`
- **Purpose:** Past deployments with logs, status, and credit costs
- **Content** (400-800 tokens, paginated with `?limit=10&cursor=xxx`):
  ```json
  {
    "deployments": [
      {
        "id": "dep_xyz789",
        "service_id": "svc_abc123",
        "status": "completed",
        "git_repo": "github.com/user/app",
        "branch": "main",
        "commit": "a1b2c3d",
        "credits": 42.3,
        "duration": 127,
        "started": "2025-10-30T08:00:00Z",
        "completed": "2025-10-30T08:02:07Z",
        "log_url": "https://mcp.multisphere.ca/logs/dep_xyz789"
      },
      {
        "id": "dep_uvw456",
        "service_id": "svc_abc123",
        "status": "failed",
        "git_repo": "github.com/user/app",
        "branch": "develop",
        "commit": "e4f5g6h",
        "credits": 8.2,
        "duration": 45,
        "started": "2025-10-29T14:30:00Z",
        "completed": "2025-10-29T14:30:45Z",
        "error": "build_failed: npm install returned exit code 1",
        "log_url": "https://mcp.multisphere.ca/logs/dep_uvw456"
      }
    ],
    "total": 127,
    "cursor": "next_page_token_here"
  }
  ```
  - Each deployment: `id`, `service_id`, `status` (completed|failed|cancelled), `git_repo`, `branch`, `commit`, `credits`, `duration` (seconds), `started`, `completed`, `error` (if failed), `log_url`
  - Pagination: `total` count, `cursor` for next page

**Resource 8: `active_deployments`**
- **URI:** `multisphere://account/deployments/active`
- **Purpose:** Currently running deployments with real-time status
- **Content** (200-500 tokens):
  ```json
  {
    "deployments": [
      {
        "id": "dep_current",
        "service_id": "svc_abc123",
        "status": "deploying",
        "stage": "building",
        "progress": 65,
        "git_repo": "github.com/user/app",
        "branch": "main",
        "commit": "x9y8z7w",
        "credits_burned": 18.5,
        "credits_held": 50.0,
        "started": "2025-10-30T10:00:00Z",
        "elapsed": 95,
        "stream_url": "https://mcp.multisphere.ca/streams/dep_current"
      }
    ],
    "total": 1
  }
  ```
  - Each active deployment: `id`, `service_id`, `status` (deploying), `stage` (cloning|building|deploying|starting), `progress` (0-100), `git_repo`, `branch`, `commit`, `credits_burned`, `credits_held`, `started`, `elapsed` (seconds), `stream_url` (SSE endpoint)

### 3.3 Data Requirements

**What data must be stored:**
- Account metadata (account_id, credit_balance, credit_purchases with expiration dates, total_credits_burned)
- Service records (service_id, account_id, service_type, resource_spec, credit_burn_rate, provider, instance_id, status, created_at, metadata)
- Domain records (domain_id, domain_name, account_id, registered_at, expires_at, privacy_protection, nameservers, ssl_certificates)
- Deployment records (deployment_id, service_id, git_repo_url, branch, status, credits_burned, logs, created_at, completed_at)
- Credit holds (hold_id, session_id, operation, estimated_cost, held_at, expires_at)
- Integration credentials (encrypted, never exposed via MCP)
- Audit logs (operation, user, timestamp, parameters, result, credit_cost)

**What data must be exposed:**
- Via MCP tools: Service status, credit balances, deployment status, integration configuration (metadata only, no credentials)
- Via MCP resources: Service catalog with pricing, account credit summary, service inventory, domain portfolio, integration catalog, deployment history
- Via SSE streams: Real-time deployment progress, log output, credit consumption, completion status, errors

### 3.3 Integration Requirements

**Upstream Dependencies:**
- Infrastructure providers: DigitalOcean API (Phase 1), Hetzner API (optional), Cloudflare Workers API (post-acquisition)
- Domain registrars: Namecheap API (Phase 1), OpenSRS API (alternative)
- SSL certificate authorities: Let's Encrypt ACME protocol (free certs), Sectigo API (commercial certs)
- SaaS provider APIs: Stripe Connect, Shopify Partner API, SendGrid API, Twilio API, Zendesk API
- Git hosting: GitHub API, GitLab API, Bitbucket API (read-only for repository cloning)

**Downstream Consumers:**
- MCP clients: Claude Code, GitHub Copilot, Codex, Cursor (via MCP protocol)
- Monitoring systems: Prometheus (metrics), Grafana (dashboards), Sentry (error tracking)
- Audit logging: Structured JSON logs to centralized logging system
- Billing system: Credit consumption events for financial reporting

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **MCP Tool Response Time:** p95 < 500ms for all synchronous tools (excluding long-running operations like deployments)
- **Deployment Speed:** Complete Node.js app deployment (clone + build + deploy) < 5 minutes for standard apps
- **SSE Stream Latency:** Progress events delivered within 200ms of occurrence
- **Token Efficiency:** Average MCP tool response < 500 tokens, typical responses 200-300 tokens
- **Streaming Token Efficiency:** SSE events < 50 tokens per event (progress, log, credit_update)
- **Database Query Performance:** p95 < 50ms for account/service queries
- **Concurrent Operations:** Support 100+ concurrent deployments without degradation
- **Rollback Speed:** Zero-downtime rollback completes in < 60 seconds

### 4.2 Security

- **Authentication:** JWT tokens with 1-hour expiry, refresh tokens with 30-day expiry, secure token storage
- **Authorization:** Role-based access control (account owners only), service-level permissions
- **Data Protection:** All credentials encrypted at rest using AES-256, TLS 1.3 for all API communication, encrypted database backups
- **Audit Logging:** All operations logged with timestamp, user, action, parameters (excluding credentials), result, stored for 7 years
- **Port Restrictions:** Firewall rules enforced at infrastructure level (not just software), SMTP (25) and SMB (445) permanently blocked
- **Rate Limiting:** 100 provisioning requests per hour per account, 1000 MCP tool calls per hour per account, stricter limits for free tier
- **Secrets Management:** No credentials in code, environment variables, or logs, use dedicated secrets vault (HashiCorp Vault or AWS Secrets Manager)
- **Vulnerability Scanning:** Automated dependency scanning (Dependabot), container image scanning, quarterly penetration testing

### 4.3 Reliability

- **Availability:** Target 99.9% uptime (43 minutes downtime per month allowed)
- **Error Handling:** All operations have explicit error responses, credit holds released on any error, deployment failures rollback automatically
- **Recovery:** Long-running operations checkpoint progress every 30 seconds, operations resume after server restart, state persisted to database
- **Data Integrity:** ACID-compliant database transactions for credit operations, foreign key constraints for referential integrity, regular integrity checks
- **Failover:** Stateless MCP server design (horizontal scaling), database replication with automatic failover, load balancer health checks every 10 seconds
- **Monitoring:** Real-time alerts for service failures, deployment failures, credit system errors, provider API outages
- **Backup:** Daily database backups retained for 30 days, point-in-time recovery capability, backup restoration tested monthly

### 4.4 Scalability

- **Current Scale (A0-A1):** 10-100 customers, 50-500 active services, 10-50 concurrent deployments
- **Phase 2 Scale (A2):** 100-1000 customers, 500-5000 active services, 50-200 concurrent deployments
- **Phase 3 Scale (A3):** 1000-10000 customers, 5000-50000 active services, 200-1000 concurrent deployments
- **Bottlenecks:**
  - Database connection pooling (100 connections at A1, 1000 at A2)
  - Provider API rate limits (DigitalOcean: 5000 requests/hour)
  - SSE stream memory consumption (limit 1000 concurrent streams per server)
- **Scaling Strategy:** Horizontal scaling of stateless MCP servers, database read replicas for queries, deployment workers in separate process pool, provider API request queuing

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- **Constraint 1:** Must use DigitalOcean as primary provider for Phase 1 due to Partner Pod strategic relationship and fast MVP development
- **Constraint 2:** Cannot provide custom nameserver branding (ns1.multisphere.net) on Cloudflare free tier - must use Cloudflare nameservers or paid Enterprise plan
- **Constraint 3:** Let's Encrypt SSL certificates show "Let's Encrypt" in browser, not "mcpworks SSL" (transparency requirement, cannot brand)
- **Constraint 4:** Stripe Connect requires business verification for live mode (test mode available immediately, live mode 1-3 business days)
- **Constraint 5:** Shopify Partner API requires partner account approval (application process 3-5 business days)

### 5.2 Business Constraints

- **Budget:** A0 phase $8.5K-$10K, A1 phase $50K-$100K (constrains infrastructure testing, limits paid service tier experiments)
- **Timeline:** Must reach A1 by Month 6 (50K MRR), A2 by Month 12 (150K MRR) - acquisition conversations begin at A2
- **Resources:** Solo founder (Simon) for A0-A1, +CEO at A1, +PM (Director of Ops & AI/LLM) at A0 - limited dev capacity requires prioritization
- **Legal:** Must obtain legal opinion on money transmission licensing (GO/NO-GO gate), insurance must be available for AI-automated provisioning (GO/NO-GO gate)

### 5.3 Assumptions

- **Assumption 1:** AI assistants will correctly parse MCP tool responses and handle SSE streaming (no manual SDK)
  - **Risk if wrong:** Integration fails, requires custom SDKs for each AI platform, delays launch 2-4 weeks
- **Assumption 2:** DigitalOcean Partner Pod discount (25%) approved at A1 phase based on $15K-25K monthly consumption
  - **Risk if wrong:** Margins compress 5-7%, pricing becomes less competitive, profitability delayed
- **Assumption 3:** Credit-based pricing resonates with developers more than traditional subscription tiers
  - **Risk if wrong:** Market rejects pricing model, requires pivot to monthly subscriptions, billing system rewrite
- **Assumption 4:** LLMs can effectively reason about credit costs in real-time and optimize deployments
  - **Risk if wrong:** Cost transparency becomes noise rather than value, simplification required
- **Assumption 5:** Shopify/Stripe/SendGrid/Twilio partner programs remain available with reasonable terms
  - **Risk if wrong:** Cannot offer complete e-commerce stack, value proposition diminished, customer acquisition harder

---

## 6. Error Scenarios & Edge Cases

### 6.1 Error Scenario: Insufficient Credits During Deployment

**Trigger:** User initiates deployment, credit balance drops below held amount mid-deployment
**Expected Behavior:** Deployment continues with held credits, alert sent to user to add credits, post-deployment credit commit may fail if refund needed
**User Experience:** AI assistant shows: "Deployment in progress (held 50 credits). Warning: Credit balance low (120 credits remaining). Please add credits to avoid service disruption."
**Recovery:** User can add credits immediately via payment link, deployment completes normally
**Logging:** Log credit_low event with user_id, current_balance, held_credits, burn_rate
**Monitoring:** Alert if 10+ users hit low credit state in 1 hour (potential pricing/billing issue)

### 6.2 Error Scenario: Provider API Outage During Provisioning

**Trigger:** DigitalOcean API returns 503 Service Unavailable during droplet creation
**Expected Behavior:** Operation retries 3 times with exponential backoff (5s, 15s, 45s), fails after retries exhausted, releases credit hold
**User Experience:** AI assistant shows: "Provisioning failed: Infrastructure provider temporarily unavailable. Please try again in a few minutes. (No credits charged)"
**Recovery:** User can retry operation immediately (credit hold released), system automatically retries after cooldown
**Logging:** Log provider_api_error with provider, endpoint, status_code, retry_count, operation_id
**Monitoring:** Alert if provider API error rate > 10% over 5 minutes (escalate to on-call)

### 6.3 Error Scenario: Deployment Build Failure (Missing Dependency)

**Trigger:** npm install fails because package 'express' not found in npm registry
**Expected Behavior:** Build fails immediately, SSE stream sends error event with build log excerpt, deployment marked as failed, credit hold released
**User Experience:** AI assistant shows: "Deployment failed during build: Package 'express' not found. Check your package.json dependencies. (8.2 credits burned for build attempt, 41.8 credits released)"
**Recovery:** User fixes package.json, AI assistant retries deployment
**Logging:** Log deployment_failed with deployment_id, stage='build', error_message, build_log_url, credits_burned
**Monitoring:** Track build failure rate by error type (missing dependency, syntax error, timeout) for common troubleshooting

### 6.4 Error Scenario: Concurrent Credit Operations (Race Condition)

**Trigger:** User initiates two deployments simultaneously, both try to hold credits from same balance
**Expected Behavior:** First operation acquires lock, holds credits successfully, second operation waits for lock release, checks remaining balance, may fail with insufficient_credits
**User Experience:** AI assistant shows for Operation 1: "Deployment started (50 credits held)", for Operation 2: "Insufficient credits: 500 credits available, 520 credits required for both operations. Please add credits or wait for Operation 1 to complete."
**Recovery:** User adds credits or waits for Operation 1 to commit/release held credits
**Logging:** Log credit_hold_contention with account_id, operation_1, operation_2, lock_wait_time
**Monitoring:** Alert if lock wait time > 5 seconds (potential deadlock)

### 6.5 Edge Case: Credit Expiration Mid-Operation

**Trigger:** User has 100 credits expiring in 5 minutes, starts deployment requiring 50 credits (30-minute duration)
**Expected Behavior:** System holds credits from non-expiring balance first, warns user about upcoming expiration, prioritizes consuming expiring credits
**User Experience:** AI assistant shows: "Deployment started (50 credits held). Note: 100 credits expiring in 5 minutes - please add credits to avoid service disruption."
**Rationale:** Prevents wasting expiring credits while ensuring operation completes
**Recovery:** User adds credits during deployment, expiring credits consumed first

### 6.6 Edge Case: Rollback to Corrupted Previous Deployment

**Trigger:** User requests rollback, but previous deployment artifacts deleted (S3 retention expired)
**Expected Behavior:** Rollback fails with clear error, suggests alternative (redeploy from git commit hash), does not attempt partial rollback
**User Experience:** AI assistant shows: "Cannot rollback: Previous deployment artifacts expired. Alternative: Redeploy from git commit abc123? (commit from 2 days ago)"
**Recovery:** User confirms redeployment from specific git commit, system treats as new deployment
**Logging:** Log rollback_failed with reason='artifacts_expired', deployment_id, alternative_offered

### 6.7 Error Scenario: Stripe API Authentication Failure

**Trigger:** User provides invalid Stripe API key during `setup_stripe_integration` call
**Expected Behavior:** API key validation fails immediately, integration not created, clear error message returned, no credit hold
**User Experience:** AI assistant shows: "Stripe integration failed: Invalid API key (starts with 'sk_test_' but authentication rejected). Please verify your key at https://dashboard.stripe.com/apikeys"
**Recovery:** User retrieves correct API key from Stripe dashboard, AI assistant retries with valid credentials
**Logging:** Log integration_auth_failed with provider='stripe', error_type='invalid_credentials', account_id
**Monitoring:** Alert if >5 authentication failures per account per hour (potential credential compromise)

### 6.8 Error Scenario: Shopify Store URL Mismatch

**Trigger:** User attempts `setup_shopify_integration` with store_url that doesn't match OAuth redirect domain
**Expected Behavior:** OAuth flow fails during redirect, user sees Shopify error page, integration status remains 'pending_auth'
**User Experience:** AI assistant shows: "Shopify integration pending: Click authorization link https://mystore.myshopify.com/admin/oauth/authorize?client_id=... to complete setup"
**Recovery:** User clicks link, completes OAuth in browser, webhook confirms success, AI assistant notifies user
**Logging:** Log integration_oauth_pending with provider='shopify', store_url, auth_url
**Monitoring:** Alert if OAuth completion rate <80% (potential UX/documentation issue)

### 6.9 Error Scenario: SendGrid Rate Limit Exceeded

**Trigger:** User's SendGrid account hits rate limit (100 emails/hour on free tier), `send_email_sendgrid` called during limit
**Expected Behavior:** SendGrid API returns 429 Too Many Requests, operation fails with descriptive error, suggests upgrade or retry timing
**User Experience:** AI assistant shows: "Email sending failed: SendGrid rate limit exceeded (100/hour limit reached). Upgrade to paid plan or wait 23 minutes for reset. (1 credit burned for API call)"
**Recovery:** User upgrades SendGrid plan or waits for rate limit reset, AI assistant retries after cooldown
**Logging:** Log third_party_rate_limit with provider='sendgrid', limit_type='hourly_email', reset_time, account_id
**Monitoring:** Track rate limit errors by provider to identify common bottlenecks

### 6.10 Error Scenario: Twilio Invalid Phone Number Format

**Trigger:** User attempts `send_sms_twilio` with malformed phone number (missing country code: "555-1234" instead of "+15551234")
**Expected Behavior:** Twilio API rejects request with 400 Bad Request, clear error message about E.164 format requirement
**User Experience:** AI assistant shows: "SMS sending failed: Invalid phone number format '555-1234'. Twilio requires E.164 format (e.g., '+15551234567'). (1 credit burned for validation attempt)"
**Recovery:** AI assistant reformats phone number to E.164, retries with corrected format
**Logging:** Log third_party_validation_error with provider='twilio', error_type='invalid_phone_format', attempted_number, account_id
**Monitoring:** Track validation error patterns to improve client-side validation

### 6.11 Error Scenario: Zendesk Webhook Delivery Failure

**Trigger:** Zendesk attempts to deliver ticket creation webhook, but mcpworks Infrastructure MCP server is restarting (maintenance window)
**Expected Behavior:** Zendesk retries webhook 3 times (5min, 15min, 1hr), MCP server recovers, processes webhook on 2nd retry
**User Experience:** AI assistant shows: "New support ticket received (delayed by 15 minutes due to system maintenance): Ticket #12345 from user@example.com"
**Recovery:** Automatic via Zendesk retry mechanism, no user action required
**Logging:** Log webhook_retry_success with provider='zendesk', retry_attempt=2, delivery_delay, event_type='ticket.created'
**Monitoring:** Alert if webhook delivery failure rate >5% (potential infrastructure issue)

### 6.12 Error Scenario: Third-Party API Sunset/Deprecation

**Trigger:** Shopify deprecates Admin API v2022-01, mcpworks still using deprecated version, API returns 426 Upgrade Required
**Expected Behavior:** System logs deprecation warning, maintains backward compatibility for 90 days, notifies all affected users, auto-migrates to new API version
**User Experience:** AI assistant shows: "Notice: Shopify integration will be upgraded to API v2024-01 on 2025-12-01. No action required - upgrade is automatic. New features will be available after upgrade."
**Recovery:** Automatic migration during maintenance window, users notified before and after
**Logging:** Log api_deprecation_notice with provider='shopify', old_version='2022-01', new_version='2024-01', migration_date, affected_accounts
**Monitoring:** Track migration success rate, rollback plan if >5% integration failures post-migration

### 6.13 Edge Case: Third-Party Credential Rotation Mid-Operation

**Trigger:** User rotates Stripe API key while payment processing is in progress (multi-step transaction)
**Expected Behavior:** Current operation completes with old key (cached), next operation uses new key (retrieved fresh), no transaction interruption
**User Experience:** AI assistant shows: "Stripe API key rotated. Current transaction will complete with existing credentials. Future transactions will use new key."
**Recovery:** Automatic - credential cache expires after current transaction, fresh credentials loaded for next operation
**Logging:** Log credential_rotation with provider='stripe', operation_in_progress, new_credential_effective_time
**Rationale:** Prevents mid-transaction failures while ensuring new credentials take effect quickly

### 6.14 Edge Case: Third-Party Service Regional Outage

**Trigger:** Shopify experiences outage in US-East region, affects 40% of stores, mcpworks receives 503 errors
**Expected Behavior:** System detects elevated error rate, switches to cached store data (read-only mode), queues write operations for retry
**User Experience:** AI assistant shows: "Shopify integration temporarily read-only due to provider outage (US-East region). Product updates will be queued and processed when service recovers (typically 5-30 minutes)."
**Recovery:** System auto-retries queued operations when Shopify returns healthy status, notifies user of queue processing completion
**Logging:** Log third_party_outage with provider='shopify', region='us-east', affected_operations, queue_depth, estimated_recovery_time
**Monitoring:** Alert if any provider error rate >20% over 10 minutes (escalate to incident response)

### 6.15 Error Scenario: Stripe Rate Limit Exceeded

**Trigger:** User's Stripe integration hits rate limit (100 req/sec live mode, 25 req/sec test mode), API returns 429 Too Many Requests with Retry-After header
**Expected Behavior:** Stripe API returns 429, operation retries with exponential backoff respecting Retry-After header, max 3 retries, if exceeded returns descriptive error
**User Experience:** AI assistant shows: "Stripe payment processing temporarily throttled: rate limit exceeded (100/sec limit reached). Retrying in 2 seconds. Consider implementing request queuing for high-volume operations. (1 credit burned for throttled request)"
**Recovery:** System automatically retries after backoff period, user can implement request batching or upgrade Stripe tier if needed
**Logging:** Log third_party_rate_limit with provider='stripe', limit_type='per_second', current_rate=100, limit_value=100, reset_time, account_id, operation
**Monitoring:** Track Stripe rate limit errors to identify high-volume integration patterns, alert if >10 rate limit hits per account per hour

### 6.16 Error Scenario: Shopify Rate Limit Exceeded (Leaky Bucket)

**Trigger:** User's Shopify integration exceeds 2 req/sec sustained rate or 40/minute burst limit, Admin API returns 429 Too Many Requests with X-Shopify-Shop-Api-Call-Limit header (e.g., "40/40")
**Expected Behavior:** System detects approaching limit via X-Shopify-Shop-Api-Call-Limit header (e.g., 38/40), slows requests proactively, if limit hit retries with exponential backoff respecting bucket refill rate (0.5 seconds per credit restored)
**User Experience:** AI assistant shows: "Shopify rate limit approaching (38/40 requests used). Slowing requests to avoid throttling." OR on 429: "Shopify API rate limit exceeded. Retrying in 5 seconds. Shopify uses leaky bucket (2 req/sec sustained). (1 credit burned for throttled request)"
**Recovery:** Automatic backoff and retry, system learns optimal request pacing per store (avg 2 req/sec)
**Logging:** Log third_party_rate_limit with provider='shopify', limit_type='leaky_bucket', bucket_current="38/40", refill_rate="2/sec", account_id, store_id
**Monitoring:** Alert if any store hits rate limit >5 times per hour (indicates need for request queuing or user education)

### 6.17 Error Scenario: Twilio Rate Limit Exceeded (Hourly SMS Quota)

**Trigger:** User's Twilio account hits hourly SMS quota (10,000/hour paid tier, 1,000/hour free tier), API returns 429 Too Many Requests with rate limit reset timestamp
**Expected Behavior:** Twilio API rejects SMS send with 429 and X-RateLimit-Reset header, operation fails with descriptive error, suggests upgrading tier or waiting for reset, optionally queues message for retry after reset
**User Experience:** AI assistant shows: "SMS sending failed: Twilio hourly rate limit exceeded (1,000/hour free tier limit reached). Next reset: 2025-10-30T11:00:00Z (45 minutes). Options: (1) Upgrade to paid plan (10,000/hour) or (2) Queue message for automatic retry after reset. (1 credit burned for API call)"
**Recovery:** User upgrades Twilio plan, waits for hourly reset, or enables message queuing for automatic retry
**Logging:** Log third_party_rate_limit with provider='twilio', limit_type='hourly_sms', limit_value=1000, messages_sent=1000, reset_time, account_id, tier='free'
**Monitoring:** Track Twilio rate limit errors by tier (free vs paid) to identify upgrade opportunities, send proactive upgrade suggestions to free tier users approaching limits

---

## 7. Token Efficiency Analysis

### 7.1 Tool Definitions

**Estimated tokens for tool schemas:** ~750 tokens total (19 tools × ~40 tokens each)

**Optimization Strategy:**
- Concise tool descriptions (<20 tokens per tool: "Deploy app from Git repo to service")
- Parameter descriptions (<10 tokens: "service_id: Target hosting service", "credits_authorized: Max credits for operation")
- Progressive disclosure: Expose tool categories first (infrastructure, deployment, integrations), detailed tools on demand
- Grouping: Related tools under namespaces (deploy.*, stripe.*, shopify.*)

### 7.2 Typical Responses

**Operation: provision_service**
**Response Size:** 120 tokens (summary) | 350 tokens (detailed with metadata)
```json
{
  "svc": "svc_abc123",
  "status": "provisioning",
  "burn": 2.5,
  "est_mo": "$54 (1800cr)",
  "eta": "2025-10-30T10:15:00Z",
  "ip": "pending"
}
```
**Optimization Strategy:** Abbreviated keys (svc vs service_id), numeric values instead of strings where possible, omit null/pending fields

**Operation: deploy_application**
**Response Size:** 80 tokens (summary) | 200 tokens (with stream_url)
```json
{
  "dep": "dep_xyz789",
  "status": "deploying",
  "stream": "https://mcp.multisphere.ca/streams/dep_xyz789",
  "est_cr": 50,
  "held": 50
}
```
**Optimization Strategy:** SSE stream URL instead of full logs, held credits shown once (not repeated in every update)

**Operation: get_credit_balance**
**Response Size:** 60 tokens
```json
{
  "avail": 1234.5,
  "held": 100,
  "burn_rate": 12.5,
  "expires": [{"amt": 500, "exp": "2025-11-15"}]
}
```

**Average tool response across all 19 tools:** ~150 tokens

### 7.3 Worst Case

**Largest possible response:** ~800 tokens (get_deployment_logs with tail_lines=50, detailed error messages)
**Mitigation:**
- Pagination: `get_deployment_logs` returns max 50 lines, provides `continue_token` for additional logs
- Streaming: Logs streamed via SSE (50 tokens per event) instead of bulk response
- Compression: Error messages summarized (full stack trace in log URL, not response)
- Progressive detail: Return summary by default, detailed view requires explicit parameter (detail_level='full')

**Token budget compliance:**
- Target: 200-1000 tokens per operation
- Actual: 60-800 tokens per operation (within target)
- Comparison: AWS MCP (hypothetical): 2000-5000 tokens per operation → mcpworks is 2.5-6x more efficient

---

## 8. Security Analysis

### 8.1 Threat Model

**Threat:** Attacker provisions services on stolen account to mine cryptocurrency
**Impact:** Integrity (unauthorized resource usage), Availability (infrastructure abuse)
**Mitigation:** Rate limiting (100 provisions per hour), anomaly detection (sudden compute-intensive provisioning), credit velocity limits (max $500 credit burn per hour without verification)
**Residual Risk:** Low (multiple defense layers)

**Threat:** Attacker uses compromised JWT to access other users' services
**Impact:** Confidentiality (access to services/data), Integrity (can modify services)
**Mitigation:** JWT tokens include account_id claim, all operations validate account ownership, short token expiry (1 hour), token rotation on privilege escalation
**Residual Risk:** Low (validated on every operation)

**Threat:** AI assistant leaks Stripe API keys via response logging
**Impact:** Confidentiality (payment processor access), Integrity (fraudulent charges)
**Mitigation:** Credentials NEVER included in MCP responses (return only account_id, dashboard_url), encrypted storage at rest, credentials only in secure vault, audit log scrubbing
**Residual Risk:** Very Low (architectural guarantee - credentials never leave vault)

**Threat:** User opens SMTP port (25) to send spam
**Impact:** Availability (IP reputation damage), Integrity (abuse of service)
**Mitigation:** Port 25 permanently blocked at firewall level, cannot be overridden via API, SSH access requires explicit approval workflow, monitoring for outbound SMTP attempts
**Residual Risk:** Very Low (infrastructure-level enforcement)

**Threat:** Attacker exploits SSE stream to DoS server (open 1000s of streams)
**Impact:** Availability (resource exhaustion)
**Mitigation:** Limit 10 concurrent streams per account, stream auto-closes after 1 hour, rate limiting on stream creation (100 streams per hour), memory limits per stream
**Residual Risk:** Low (multiple rate limits)

### 8.2 PII/Sensitive Data

**What sensitive data is involved:**
- Payment information (credit card numbers): Handled by Stripe (never touches mcpworks servers), tokenized references only
- Third-party API credentials (Stripe, Shopify, SendGrid, Twilio API keys): Encrypted at rest using AES-256, stored in HashiCorp Vault or AWS Secrets Manager, never exposed via MCP
- Domain WHOIS data (name, address, phone): Optional privacy protection via registrar (enabled by default), stored encrypted, not exposed via MCP (domain_id only)
- Deployment environment variables (may contain secrets): Stored encrypted, not included in deployment logs, not exposed via MCP responses
- User email addresses: Used for account recovery only, not shared with third parties, encrypted at rest
- Credit card billing information: Processed via Stripe, tokenized, not stored in mcpworks database

### 8.3 Compliance

**Relevant regulations:**
- **PIPEDA (Canada):** Personal information collection/use/disclosure consent required, privacy policy published, security safeguards implemented, breach notification within 72 hours
  - Compliance: Privacy policy at signup, explicit consent for data collection, encryption at rest/transit, incident response plan
- **GDPR (EU customers):** Right to access, rectification, erasure, data portability, lawful basis for processing
  - Compliance: Data export tool (JSON format), account deletion workflow (soft delete with 30-day retention), DPA with infrastructure providers
- **CCPA (California customers):** Right to know, delete, opt-out of sale (no data sales)
  - Compliance: Data disclosure on request, deletion workflow, privacy policy states "no data sales"
- **PCI-DSS (payment cards):** If handling card data directly (mcpworks does NOT - Stripe handles)
  - Compliance: N/A - tokenized references only, Stripe is PCI-compliant processor

---

## 9. Observability Requirements

### 9.1 Metrics

**Key metrics to track:**
- **mcp_tool_call_count** (counter, labels: tool_name, account_id, status): Tracks MCP tool usage for billing and debugging
- **mcp_tool_response_time** (histogram, labels: tool_name): p50, p95, p99 latencies for performance monitoring
- **mcp_tool_response_tokens** (histogram, labels: tool_name): Token efficiency tracking for optimization
- **deployment_duration** (histogram, labels: app_type, status): Tracks build + deploy time by language/framework
- **deployment_failure_rate** (gauge, labels: failure_reason): % of deployments failing by error type
- **credit_balance** (gauge, labels: account_id): Current credit balance per account for alerting
- **credit_burn_rate** (gauge, labels: account_id): Credits burned per hour for anomaly detection
- **credit_operations** (counter, labels: operation=hold|commit|release): Credit system health tracking
- **provider_api_errors** (counter, labels: provider, endpoint, status_code): Infrastructure provider reliability
- **sse_stream_count** (gauge): Active SSE streams for capacity planning
- **sse_stream_duration** (histogram): Stream lifecycle for memory optimization

### 9.2 Logging

**What must be logged:**
- **MCP tool calls:** timestamp, tool_name, account_id, parameters (sanitized - no credentials), response_status, response_time, response_tokens
- **Deployment events:** timestamp, deployment_id, stage (cloning, building, deploying, starting), status, credits_burned, error_message (if failed)
- **Credit operations:** timestamp, operation (hold, commit, release), account_id, amount, balance_before, balance_after, operation_id
- **Provider API calls:** timestamp, provider, endpoint, request_params (sanitized), response_status, response_time, retry_count
- **Security events:** timestamp, event_type (auth_failure, rate_limit, port_restriction_violation), account_id, ip_address (hashed), details
- **Integration operations:** timestamp, integration_type (stripe, shopify, sendgrid), operation (provision, configure, status), account_id, integration_id, status

**What must NOT be logged:**
- Credentials (API keys, passwords, tokens)
- Full environment variables (may contain secrets)
- Credit card numbers or payment details
- Unencrypted PII (full IP addresses - hash with salt)

**Log format:** Structured JSON with consistent schema, severity levels (DEBUG, INFO, WARN, ERROR, CRITICAL), correlation IDs for request tracing

### 9.3 Tracing

**Operations to trace:**
- **Deployment workflow:** Root span (deploy_application) → child spans (clone_repository, install_dependencies, run_build, start_application, health_check)
- **Multi-step transactions:** Root span (provision_ecommerce_stack) → child spans (provision_hosting, register_domain, setup_shopify, setup_stripe, connect_integrations)
- **Credit operations:** Root span (credit_hold) → child spans (validate_balance, acquire_lock, create_hold, release_lock)
- **Provider API calls:** Span per external API call with provider, endpoint, duration, retry_count

**Tracing backend:** OpenTelemetry-compatible (Jaeger, Tempo, or Datadog APM)

### 9.4 Alerting

**Alerts to configure:**
- **Alert 1: High deployment failure rate**
  - Condition: deployment_failure_rate > 20% over 10 minutes
  - Severity: HIGH
  - Notification: On-call engineer via PagerDuty, Slack #incidents
  - Rationale: Indicates systemic issue (provider outage, broken build system)

- **Alert 2: Provider API errors**
  - Condition: provider_api_errors > 50 per minute
  - Severity: CRITICAL
  - Notification: On-call engineer via PagerDuty, Slack #incidents
  - Rationale: Infrastructure provider outage affects all customers

- **Alert 3: Credit system errors**
  - Condition: credit_operations{operation="hold"} failures > 10 per minute
  - Severity: CRITICAL
  - Notification: On-call engineer + CTO via PagerDuty
  - Rationale: Double-charging or credit loss risk

- **Alert 4: SSE stream capacity**
  - Condition: sse_stream_count > 800 (80% of 1000 limit)
  - Severity: MEDIUM
  - Notification: Slack #engineering
  - Rationale: Approaching capacity, need horizontal scaling

- **Alert 5: Account low credit balance**
  - Condition: credit_balance < (burn_rate * 24 hours)
  - Severity: LOW (user notification, not operational alert)
  - Notification: Email to user, in-app notification
  - Rationale: Proactive user communication prevents service disruption

### 9.5 Third-Party Integration Observability

**Additional metrics for third-party integrations:**
- **integration_api_call_count** (counter, labels: provider, operation, status): Track API usage per integration (Stripe, Shopify, etc.)
- **integration_api_latency** (histogram, labels: provider, operation): p50, p95, p99 latencies for third-party APIs
- **integration_api_errors** (counter, labels: provider, error_type, status_code): Track authentication, rate limiting, outage errors
- **integration_credits_burned** (counter, labels: provider, operation): Credits consumed per integration API call (enables cost tracking per provider/operation)
- **integration_credits_per_operation** (histogram, labels: provider, operation): Credit cost distribution per operation type (p50, p95, p99 for cost optimization)
- **webhook_received_count** (counter, labels: provider, event_type): Webhook delivery tracking
- **webhook_processing_time** (histogram, labels: provider, event_type): Webhook processing latency
- **webhook_signature_failures** (counter, labels: provider): Security monitoring for invalid webhooks
- **webhook_delivery_failures** (counter, labels: provider, event_type, failure_reason): Failed webhook deliveries (timeout, connection_refused, 5xx errors)
- **webhook_delivery_success_rate** (gauge, labels: provider): Percentage of successful webhook deliveries (0-100), calculated over 10-minute window
- **integration_health_status** (gauge, labels: provider): 1=healthy, 0=degraded (based on error rate threshold)
- **integration_auth_failures** (counter, labels: provider): Track credential issues for proactive rotation
- **integration_operation_queue_depth** (gauge, labels: provider): Number of queued operations waiting for provider recovery during outages
- **integration_operation_queue_duration** (histogram, labels: provider): Time operations spend in queue before processing (p50, p95, p99)

**Additional logging for third-party integrations:**
- **Integration API calls:** timestamp, provider, operation, account_id, integration_id, request_id (provider's trace ID), response_status, latency, retry_count, error_code, credits_burned
- **Webhook events:** timestamp, provider, event_type, event_id, signature_valid, processing_status, processing_time, duplicate_detected
- **Credential operations:** timestamp, operation (create, rotate, expire), provider, integration_id, account_id, expiration_date (if applicable)
- **Rate limit events:** timestamp, provider, operation, limit_type (hourly, daily), limit_remaining, reset_time, account_id, queued (boolean), queue_position (integer)

**Additional alerts for third-party integrations:**
- **Alert 6: Third-party integration outage**
  - Condition: integration_api_errors{provider=X, error_type="outage"} > 20% error rate over 10 minutes
  - Severity: HIGH
  - Notification: On-call engineer, Slack #incidents, status page update
  - Rationale: Third-party outage affects customer operations, requires status communication

- **Alert 7: Integration authentication failures**
  - Condition: integration_auth_failures{provider=X} > 5 per account per hour
  - Severity: MEDIUM
  - Notification: Email to account owner, in-app notification
  - Rationale: Likely invalid/expired credentials, proactive user notification prevents service disruption

- **Alert 8: Webhook signature failures**
  - Condition: webhook_signature_failures{provider=X} > 10 per hour
  - Severity: HIGH
  - Notification: On-call engineer, security team
  - Rationale: Potential webhook replay attack or provider configuration issue

- **Alert 9: Third-party rate limiting**
  - Condition: integration_api_errors{error_type="rate_limit"} > 5 per account per hour
  - Severity: MEDIUM
  - Notification: Email to account owner with upgrade recommendation
  - Rationale: User hitting third-party plan limits, proactive upgrade suggestion improves experience

- **Alert 10: Webhook delivery failures**
  - Condition: webhook_delivery_success_rate{provider=X} < 95% over 10 minutes
  - Severity: MEDIUM
  - Notification: Slack #engineering, email to integration owner
  - Rationale: Persistent delivery failures indicate webhook endpoint issues, provider problems, or network connectivity issues requiring investigation

---

## 10. Testing Requirements

### 10.1 Unit Tests

**Must test:**
- Credit system hold/commit/release logic (race conditions, concurrent operations, expiration handling)
- Provider abstraction layer (DigitalOcean, Hetzner, Cloudflare adapters, pricing calculations)
- MCP tool parameter validation (required fields, type checking, range validation)
- Token estimation functions (verify <500 token target for all tool responses)
- Error handling (insufficient credits, provider API failures, invalid parameters)
- Transaction rollback compensation logic (provision service → deprovision service symmetry)

**Coverage target:** 80% line coverage for business logic (credit system, provider abstraction, tool implementations)

### 10.2 Integration Tests

**Must test:**
- MCP protocol compliance (stdio, SSE, WebSocket transports)
- DigitalOcean API integration (create droplet, get status, delete droplet, handle rate limits)
- Credit hold → operation → commit workflow (end-to-end with real credit operations)
- SSE streaming (deployment starts → progress events → log events → completed event)
- Transactional workflows (e-commerce setup: all succeed OR all rollback)
- Error propagation (provider API 503 → MCP error response with credit release)

**Test environment:** Staging infrastructure with isolated DigitalOcean test project, test credit accounts with 10,000 credits, mock Stripe/Shopify APIs

### 10.2.1 Third-Party Integration Tests

**Must test for each integration (Stripe, Shopify, SendGrid, Twilio, Zendesk):**

**Authentication & Setup:**
- Valid API key/credentials → integration created successfully
- Invalid API key → immediate rejection with descriptive error (no credit hold)
- OAuth flow (Shopify) → redirect → callback → token exchange → integration activated
- OAuth domain mismatch (Shopify) → redirect fails → user sees Shopify error → integration remains pending_auth → retry with correct store_url succeeds (regression test for Section 6.8)
- Credential rotation → old credentials cached for in-flight operations, new credentials used for next operation
- Credential expiration → proactive refresh before expiration (7 days warning)

**API Operations:**
- **Stripe:** Create customer, process payment, list transactions, handle webhooks (payment.succeeded, payment.failed)
- **Shopify:** Create product, update inventory, list orders, handle webhooks (order.created, product.updated)
- **SendGrid:** Send email, validate email addresses, handle bounces/complaints via webhooks
- **Twilio:** Send SMS with E.164 phone validation, receive SMS webhooks, handle delivery status
- **Zendesk:** Create ticket, list tickets, update ticket status, handle webhooks (ticket.created, comment.added)

**Error Handling:**
- Rate limiting (429 errors) → retry with exponential backoff, surface limit to AI assistant
- API outage (503 errors) → retry 3 times with backoff, graceful degradation with cached data
- Invalid parameters (400 errors) → client-side validation before API call, descriptive error messages
- Authorization errors (401/403) → credential refresh attempt, notify user if credentials invalid
- API deprecation (426 errors) → log deprecation notice, maintain compatibility, auto-migrate within 90 days

**Webhook Handling:**
- Webhook signature verification (all providers use HMAC or similar)
- Duplicate webhook detection (idempotency via event_id tracking)
- Webhook retry tolerance (handle 3+ retries from provider without duplicate processing)
- Out-of-order webhook handling (e.g., order.fulfilled arrives before order.created)
- Webhook replay attacks (reject signatures >5 minutes old)

**Observability:**
- Integration health monitoring (API call success rate, p95 latency)
- Webhook processing metrics (delivery rate, processing time, error rate)
- Cost tracking (credits burned per third-party API call type)
- Alert thresholds (error rate >10% over 5 minutes, webhook delivery failures >5%)

**Test tools:** Stripe Test Mode, Shopify Development Store, SendGrid sandbox, Twilio test credentials, Zendesk sandbox, webhook.site for webhook testing

### 10.3 E2E Tests

**User workflows to test:**
- **Happy path: Deploy Node.js app**
  - User: "Deploy my app from https://github.com/user/my-app.git"
  - Expected: Provision service → deploy application → return URL → 95%+ success rate
- **Happy path: Launch e-commerce store**
  - User: "Create an online pottery store"
  - Expected: Provision hosting → register domain → setup Shopify → setup Stripe → connect integrations → return admin URLs
- **Error path: Insufficient credits**
  - User: "Deploy my app" (credit balance: 10 credits, deployment requires 50 credits)
  - Expected: AI shows "Insufficient credits: 10 available, 50 required. Please add credits." → No resources provisioned
- **Error path: Deployment build failure**
  - User: "Deploy my app" (app has invalid package.json)
  - Expected: Build fails → SSE stream sends error event with build log → credits released → AI shows error with recovery suggestion
- **Rollback path: Broken deployment**
  - User: "App is broken, rollback to previous version"
  - Expected: Rollback completes in <60 seconds → app restored → minimal credits charged

**Test automation:** Playwright for browser-based AI assistant simulation, MCP protocol client library for direct tool testing

### 10.4 Performance Tests

**Load tests:**
- **Scenario 1: 100 concurrent deployments**
  - Load: 100 users simultaneously deploy Node.js apps
  - Success criteria: 95%+ completion rate, p95 deployment time < 8 minutes, no credit system errors
- **Scenario 2: Sustained provisioning load**
  - Load: 500 service provisioning requests over 10 minutes (50 req/min)
  - Success criteria: All requests complete, p95 response time < 2 seconds, no provider API rate limit errors
- **Scenario 3: SSE stream capacity**
  - Load: 800 concurrent SSE streams (80% of capacity)
  - Success criteria: All streams deliver events, p95 event latency < 300ms, memory usage < 4GB

**Load testing tools:** Locust (Python load testing), k6 (SSE stream testing)

---

## 11. Future Considerations

### 11.1 Phase 2 Enhancements

**Not in this spec, but planned:**
- **Multi-region deployments:** Deploy application to multiple geographic regions (Toronto, New York, London) for global low-latency access
- **Auto-scaling:** AI-triggered automatic resource scaling based on traffic patterns (requires monitoring integration)
- **Database managed services:** PostgreSQL, MySQL, Redis provisioning (Phase 1 is compute-only)
- **CDN integration:** Cloudflare CDN provisioning for static asset acceleration
- **Custom domains on Cloudflare:** Cloudflare Enterprise partnership for ns1.multisphere.net custom nameservers
- **Additional integrations:** Auth0/Clerk (authentication), Segment (analytics), Algolia (search), GitHub Actions (CI/CD)
- **Team accounts:** Multi-user accounts with role-based access control (owner, admin, developer, viewer)
- **Billing tiers:** Free tier (500 credits/month with credit card validation), Starter ($24/month), Pro ($99/month), Enterprise (custom)

### 11.2 Known Limitations

**What this spec doesn't address:**
- **Limitation 1: Single-provider Phase 1 (DigitalOcean only)**
  - Why acceptable: Fast MVP development, provider abstraction layer enables future multi-provider
  - When we'll address: A2 phase (Month 7-12) - add Hetzner, Cloudflare providers
- **Limitation 2: CAD-only billing**
  - Why acceptable: Canadian business, simplifies compliance and tax
  - When we'll address: Post-acquisition or if >20% customers request USD/EUR (customer feedback dependent)
- **Limitation 3: No database managed services**
  - Why acceptable: Compute provisioning is 80% of use cases, databases can run in containers initially
  - When we'll address: A1 phase (Month 3-6) - add PostgreSQL, MySQL, Redis tools
- **Limitation 4: No advanced monitoring/alerting provisioning**
  - Why acceptable: Basic service monitoring sufficient for Phase 1, customers can integrate own tools
  - When we'll address: A2 phase (Month 7-12) - add Datadog, New Relic, Sentry integrations
- **Limitation 5: No custom Docker image deployment**
  - Why acceptable: Git-based deployment covers 90% of use cases, Dockerfile support via buildpack detection
  - When we'll address: A1 phase (Month 3-6) - add Docker registry integration (Docker Hub, ECR)

---

## 12. Spec Completeness Checklist

**Before moving to Plan phase:**

- [ ] Clear user value proposition stated
- [ ] Success criteria defined and measurable
- [ ] All functional requirements enumerated
- [ ] All constraints documented
- [ ] Error scenarios identified
- [ ] Security requirements specified
- [ ] Performance requirements quantified
- [ ] Token efficiency requirements stated
- [ ] Testing requirements defined
- [ ] Observability requirements defined
- [ ] Reviewed for Constitution compliance
- [ ] Logic checked (internally consistent)
- [ ] Peer reviewed (if team > 1)

---

## 13. Approval

**Status:** Draft

**Approvals:**
- [ ] CTO (Simon Carr)
- [ ] CEO (if business impact)
- [ ] Security Review (if sensitive data/operations)

**Approved Date:** [Pending]
**Next Review:** [Pending] (or when requirements change)

---

## Changelog

**v1.3.0 (2025-10-31):**
- **FIX #3 FOLLOW-UPS:** Completed 4 integration observability gaps identified in Codex review
  - Added webhook delivery tracking metrics (webhook_delivery_failures counter, webhook_delivery_success_rate gauge) with Alert 10 (<95% delivery rate over 10 minutes)
  - Added credit tracking for third-party API calls (integration_credits_burned counter, integration_credits_per_operation histogram, credits_burned logging field)
  - Added 3 provider-specific rate limit error scenarios (Section 6.15 Stripe 100/sec, Section 6.16 Shopify 2/sec leaky bucket, Section 6.17 Twilio 1K-10K/hour SMS quota)
  - Added queue depth metrics for provider outages (integration_operation_queue_depth gauge, integration_operation_queue_duration histogram, queued/queue_position logging fields)
  - Added Shopify OAuth domain mismatch regression test to Section 10.2.1 (references Section 6.8 error scenario)
- **Status:** All Codex ultrareview Fix #3 follow-ups resolved
- **Total additions:** ~200 lines resolving integration monitoring and error scenario gaps

**v1.2.0 (2025-10-30):**
- **FIX #1 FOLLOW-UPS:** Completed 5 schema definition gaps identified in Codex review
  - Added complete JSON schemas for Resources 2-8 (account_credits, service_inventory, domain_portfolio, integration_catalog, active_integrations, deployment_history, active_deployments)
  - Defined environment_vars object schema (max 100 vars, key 1-64 chars, value max 4KB, encryption at rest)
  - Defined initial_products and variants schemas for Shopify tools (max 50 products, max 100 variants per product)
  - Added SSE event payload schemas for deploy_application and rollback_deployment (progress, log, credit_update, completed, error events)
  - Expanded setup_twilio_sms parameters (number_type, capabilities, webhook_url, messaging_brand for A2P 10DLC)
  - Defined metrics object schema in get_service_status (cpu_pct, mem_pct, disk_pct, net_in_mbps, net_out_mbps, req_per_sec)
  - Clarified burn_change format in scale_service (numeric value, calculation: burn_new - burn_old)
- **FIX #4 FOLLOW-UPS:** Completed 5 credit state machine clarifications
  - Reconciled RELEASED state (now a hold record status, not a credit balance state)
  - Clarified max_duration_hours as optional parameter with 4-hour default
  - Defined idempotency for conflicting payloads (commit rejects different amounts, release ignores different reasons)
  - Added lock_timeout failure cases to commit and release operations
  - Documented 3 concurrent race scenarios (simultaneous holds, expiration races, multiple client attempts)
- **Status Update:** Changed from "Ready for Review" to "Ready for Implementation"
- **Total additions:** ~400 lines resolving all Fix #1 and Fix #4 Codex follow-up issues

**v1.1.0 (2025-10-30):**
- **CRITICAL FIX #1:** Added Section 3.2 "MCP Tool & Resource Catalog" (~420 lines)
  - Defined all 19 MCP tools with complete schemas (parameters, returns, error codes, token estimates)
  - Defined all 8 MCP resources with URIs and content descriptions
  - Addresses Codex feedback: "REQ-MCP-002 demands 19 tools, yet spec never enumerates schemas"
- **CRITICAL FIX #2:** Resolved database scope contradiction
  - Clarified line 46: "managed databases in Phase 2 per Limitation 3"
  - Updated Tool 1 service_type parameter to exclude "database" in Phase 1
  - Updated Resource 1 service catalog example to show storage instead of database
- **CRITICAL FIX #3:** Added comprehensive third-party integration error scenarios and testing
  - Added Section 6.7-6.14: 8 new error scenarios for Stripe, Shopify, SendGrid, Twilio, Zendesk integrations
  - Added Section 10.2.1: Third-Party Integration Tests (authentication, API operations, error handling, webhooks, observability)
  - Added Section 9.5: Third-Party Integration Observability (8 new metrics, 4 new alerts, comprehensive logging)
- **CRITICAL FIX #4:** Detailed credit hold/commit/release state machine
  - Added "Credit Transaction State Machine" subsection under REQ-CREDIT-002
  - Documented 4 states (AVAILABLE, HELD, COMMITTED, RELEASED) with state transition diagram
  - Specified Hold/Commit/Release operations with inputs, preconditions, actions, outputs, failure cases
  - Defined automatic expiration, concurrent operation handling, consistency guarantees, audit trail
  - Addresses Codex feedback: "No state model, timeouts, or idempotency specified"
- **Status Update:** Changed from "Draft" to "Ready for Review"
- **Total additions:** ~750 lines addressing all Codex critical issues

**v1.0.0 (2025-10-30):**
- Initial comprehensive specification
- Converted from informal v0.4.0 draft to formal TEMPLATE.md structure
- Added complete user scenarios, functional requirements, security analysis, testing requirements
- Aligned with CONSTITUTION.md principles (spec-first, token efficiency, streaming, transaction safety, provider abstraction)
