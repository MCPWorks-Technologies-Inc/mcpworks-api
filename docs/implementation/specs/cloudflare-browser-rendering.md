# Cloudflare Browser Rendering Integration - Specification

**Version:** 0.2.0 (Conditionally Approved)
**Created:** 2026-03-06
**Status:** Conditionally Approved (pending Constitution compliance review)
**Spec Author:** Simon Carr
**Reviewers:** CEO, CFO, CPO, CTO, CLO, CMO
**Target Phase:** A1

---

## 1. Overview

### 1.1 Purpose

Integrate Cloudflare Browser Rendering as a backend for outbound web interactions — enabling MCPWorks functions to navigate websites, extract content, take screenshots, and interact with pages on behalf of AI assistants.

### 1.2 User Value

AI assistants currently cannot interact with arbitrary websites through MCPWorks. This capability enables functions that scrape data, monitor pages, fill forms, verify URLs, capture screenshots, and extract structured data from JS-heavy sites — all executed at Cloudflare's edge with no infrastructure for the user to manage.

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] A MCPWorks function can navigate to a URL and return page content
- [ ] A MCPWorks function can take a screenshot of a rendered page
- [ ] A MCPWorks function can extract structured data from a JS-rendered page
- [ ] Browser sessions are isolated per-execution (no state leakage between users)
- [ ] Usage is metered against the account's execution quota

### 1.4 Scope

**In Scope (Phase 1):**
- Cloudflare Browser Rendering API integration as a provider
- Page navigation, content extraction, screenshot capture
- Wait-for-selector / wait-for-navigation patterns
- Usage metering (each browser render = 1 execution)

**Phase 2 (separate spec):**
- Form interaction (click, type, select) — deferred per board review (abuse risk, complexity)
- PDF generation from web pages
- Authenticated sessions (cookie/header injection)
- Scheduled monitoring with diff detection

**Out of Scope:**
- Long-lived browser sessions or persistent cookies across executions
- Browser extensions or custom Chrome profiles
- Websocket proxying or live browser streaming to end users
- Replacing the existing Code Sandbox backend (this is a new backend type)

---

## 2. User Scenarios

### 2.1 Primary Scenario: Web Content Extraction

**Actor:** AI Assistant (via MCP)
**Goal:** Extract structured data from a JavaScript-rendered website
**Context:** User asks AI to get pricing information from a competitor's website

**Workflow:**
1. AI assistant calls `execute_function` with a browser-rendering function
2. API validates usage limits, routes to Cloudflare Browser Rendering backend
3. Worker spawns headless browser, navigates to target URL
4. Page renders (including JS), content is extracted per function definition
5. Browser session is destroyed
6. Structured data returned to AI assistant

**Success:** Extracted data returned in <10 seconds, browser session cleaned up
**Failure:** Target site blocks request — return structured error with reason (timeout, blocked, DNS failure)

### 2.2 Secondary Scenario: Screenshot Capture

**Actor:** AI Assistant (via MCP)
**Goal:** Capture a visual snapshot of a web page
**Context:** User asks AI to check if their deployment looks correct

**Workflow:**
1. AI assistant calls function with URL and viewport parameters
2. Browser navigates, waits for page load
3. Screenshot captured as PNG/JPEG
4. Image stored in R2, presigned URL returned
5. AI assistant can view or relay the screenshot to user

**Success:** Screenshot returned as accessible URL within 15 seconds
**Failure:** Page fails to load — return error with HTTP status from target

---

## 3. Functional Requirements

### 3.1 Core Capabilities

**REQ-BR-001: Page Navigation and Content Extraction**
- **Description:** Must navigate to a URL, wait for full render (including JS), and return page content as text/HTML/markdown
- **Priority:** Must Have
- **Rationale:** Core value proposition — websites are increasingly JS-rendered and require a real browser
- **Acceptance:** Function receives URL, returns rendered page content within 15s p95

**REQ-BR-002: Screenshot Capture**
- **Description:** Must capture viewport or full-page screenshots in PNG/JPEG format
- **Priority:** Must Have
- **Rationale:** Visual verification is a common AI assistant need
- **Acceptance:** Screenshot stored in R2, presigned URL returned with configurable expiry

**REQ-BR-003: Session Isolation**
- **Description:** Each execution must use a fresh browser context with no shared state
- **Priority:** Must Have
- **Rationale:** Security — prevent data leakage between users/executions
- **Acceptance:** No cookies, localStorage, or cache persists between executions

### 3.2 Data Requirements

**What data must be stored:**
- Execution metadata (function_id, account_id, target_url, duration_ms, status)
- Screenshot/PDF artifacts in R2 (TTL: 24 hours default, configurable)
- No page content stored beyond the response — ephemeral by default

**What data must be exposed:**
- Via function response: extracted content, screenshot URLs, execution timing
- Via usage API: browser rendering executions counted against quota

### 3.3 Integration Requirements

**Upstream Dependencies:**
- Cloudflare Workers (execution environment)
- Cloudflare Browser Rendering API (headless Chromium)
- Cloudflare R2 (artifact storage for screenshots/PDFs)

**Downstream Consumers:**
- MCPWorks API execution router (dispatches to this backend)
- Usage tracking system (metering)
- Audit logging (compliance)

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **Response Time:** p95 < 15 seconds for page load + content extraction
- **Response Time:** p95 < 20 seconds for screenshot capture (includes R2 upload)
- **Throughput:** 50 concurrent browser sessions per account (Cloudflare limit)
- **Token Efficiency:** Content extraction response < 500 tokens (use markdown compression, truncation)

### 4.2 Security

- **Authentication:** Standard MCPWorks API key / JWT — no additional auth for browser rendering
- **Authorization:** Account must be on Builder tier or above (not available on Free tier)
- **URL Allowlisting:** Optional per-function URL pattern restrictions (e.g., only `*.example.com`)
- **Blocked Targets:** Cannot target `localhost`, `127.0.0.1`, `10.*`, `172.16-31.*`, `192.168.*`, MCPWorks internal domains, or cloud metadata endpoints (`169.254.169.254`)
- **Data Protection:** No credentials or sensitive form data logged; artifacts auto-expire
- **Acceptable Use:** ToS must prohibit unauthorized access, scraping sites that prohibit it via robots.txt or ToS, and use for harassment or surveillance (CLO action item)
- **Audit:** Every browser execution logged with account_id, function_id, target_url (query params stripped), status, duration

### 4.3 Reliability

- **Availability:** Inherits Cloudflare Workers SLA (99.99%)
- **Error Handling:** Timeout after 30 seconds, return structured error; retry logic is caller's responsibility
- **Recovery:** Stateless — no recovery needed, just re-execute
- **Data Integrity:** Artifacts in R2 are immutable once written; TTL handles cleanup

### 4.4 Scalability

- **Current Scale:** 50 concurrent sessions, sufficient for A0-A1
- **Future Scale:** Cloudflare scales horizontally; no architecture changes needed
- **Bottlenecks:** Cloudflare Browser Rendering has per-account concurrency limits; monitor and request increases as needed

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- Must use Cloudflare Workers as execution environment (required for Browser Rendering API access)
- Browser Rendering is usage-based pricing — draws from $5K Cloudflare startup credits
- Puppeteer API subset only — not full Chrome DevTools Protocol
- Maximum page load timeout: 30 seconds (Cloudflare Worker CPU time limits)

### 5.2 Business Constraints

- **Budget:** Covered by Cloudflare for Startups credits ($5K, expires March 2027); internal cap of $1K for browser rendering in year 1
- **Timeline:** Phase 1 (navigation + extraction + screenshots) aligned with A1 milestone
- **Tier Restriction:** Builder ($29/mo) and above — Free tier does not include browser rendering

### 5.3 Assumptions

- Cloudflare Browser Rendering API remains stable and available in Workers
- R2 storage for artifacts is negligible cost (screenshots are small, TTL'd)
- AI assistants will primarily use this for read-only web interaction, not heavy automation
- **Risk if wrong:** If Cloudflare deprecates Browser Rendering, need to fall back to self-hosted Playwright (DigitalOcean)

---

## 6. Error Scenarios & Edge Cases

### 6.1 Error Scenario: Target Site Blocks Request

**Trigger:** Target website returns 403, CAPTCHA, or bot detection page
**Expected Behavior:** Return structured error with HTTP status and indication of bot detection
**User Experience:** AI assistant receives actionable error — can inform user the site blocks automated access
**Recovery:** User can try different URL or accept limitation
**Logging:** Log target_url, response_status, bot_detection flag
**Monitoring:** Track block rate per domain; alert if >50% of requests to a domain are blocked

### 6.2 Error Scenario: Page Load Timeout

**Trigger:** Target page does not complete loading within 30 seconds
**Expected Behavior:** Return partial content if available, plus timeout error
**User Experience:** AI assistant receives what loaded plus a warning
**Recovery:** User can retry or accept partial content
**Logging:** Log target_url, timeout_ms, partial_content_available flag

### 6.3 Edge Case: Very Large Pages

**Scenario:** Page content exceeds token-efficient response size (>5000 tokens of text)
**Expected Behavior:** Truncate to configurable limit (default 2000 tokens), indicate truncation
**Rationale:** Protects token efficiency; caller can request specific selectors instead of full page

### 6.4 Edge Case: Redirect Chains

**Scenario:** URL redirects through 5+ hops
**Expected Behavior:** Follow up to 10 redirects, return final page content plus redirect chain metadata
**Rationale:** Common pattern; transparent to caller but logged for debugging

---

## 7. Token Efficiency Analysis

### 7.1 Typical Responses

**Operation:** Extract page content
**Response Size:** 200-500 tokens (markdown-compressed, truncated)
**Optimization Strategy:** Return markdown not HTML; strip nav/footer/ads; respect max_tokens parameter

**Operation:** Screenshot capture
**Response Size:** 100 tokens (presigned URL + metadata)
**Optimization Strategy:** URL reference, not inline image data

### 7.2 Worst Case

**Largest possible response:** 2000 tokens (full page content at max truncation limit)
**Mitigation:** Configurable max_content_length; CSS selector targeting for specific elements

---

## 8. Security Analysis

### 8.1 Threat Model

**Threat:** SSRF — User crafts URL targeting internal infrastructure
**Impact:** Confidentiality (access internal services)
**Mitigation:** Block private IP ranges, MCPWorks domains, and cloud metadata endpoints (169.254.169.254)
**Residual Risk:** Low (Cloudflare Workers already isolate from internal infra)

**Threat:** Data exfiltration — Function extracts sensitive data from authenticated pages
**Impact:** Confidentiality
**Mitigation:** No persistent cookies/auth; each session is fresh; audit logging of all target URLs
**Residual Risk:** Low (no credentials injected by default)

**Threat:** Abuse — Using browser rendering for DDoS or scraping at scale
**Impact:** Availability (of target sites), reputation risk
**Mitigation:** Rate limiting per account; concurrency cap; monitoring for high-volume single-domain targeting
**Residual Risk:** Medium (standard for any browser automation service)

### 8.2 PII/Sensitive Data

- **Target page content:** Ephemeral, not stored beyond response; artifacts TTL'd in R2
- **Target URLs:** Logged for audit; query params stripped in logs (mandatory, not optional)

### 8.3 Compliance

- **PIPEDA (Canada):** No PII stored beyond ephemeral execution; audit log retention 90 days
- **GDPR (if EU customers):** Artifacts auto-delete via TTL; no persistent user tracking

---

## 9. Observability Requirements

### 9.1 Metrics

- `browser_rendering.executions_total` — Counter by account, status (success/error/timeout)
- `browser_rendering.duration_seconds` — Histogram of execution duration
- `browser_rendering.content_size_tokens` — Histogram of response content size
- `browser_rendering.blocked_rate` — Percentage of requests blocked by target sites

### 9.2 Logging

**What must be logged:**
- Execution start/end: account_id, function_id, target_url (sanitized), duration_ms, status
- Errors: error_type, http_status, partial_content_available

**What must NOT be logged:**
- Form input values, page content, cookie values, authentication tokens

### 9.3 Alerting

- Alert if error rate > 20% over 5 minutes (investigate browser rendering API issues)
- Alert if single account exceeds 500 executions/hour (potential abuse)
- Alert if Cloudflare credits drop below $1,000 remaining

---

## 10. Testing Requirements

### 10.1 Unit Tests

- URL validation (block private IPs, internal domains)
- Content truncation logic
- Response serialization (markdown compression)
- Artifact TTL configuration

### 10.2 Integration Tests

- Worker → Browser Rendering API → content extraction (against test page)
- Worker → R2 upload → presigned URL generation
- API → Worker dispatch → response return
- Usage metering increments on successful execution

### 10.3 E2E Tests

- AI assistant calls browser rendering function, receives content
- Screenshot function returns accessible R2 URL
- Free tier account receives tier restriction error
- SSRF attempt returns blocked error

### 10.4 Performance Tests

- 10 concurrent browser sessions completing within p95 targets
- Sustained load of 100 executions/minute for 10 minutes

---

## 11. Future Considerations

### 11.1 Phase 2 Enhancements

**Deferred from Phase 1 per board review (2026-03-06):**
- **DOM interaction:** Click, type, select, form submission — requires acceptable use policy and abuse mitigation design
- **PDF generation:** Generate PDF from rendered pages, store in R2

**Planned:**
- **Authenticated sessions:** Allow functions to inject cookies/headers for authenticated scraping (requires credential vault integration)
- **Scheduled monitoring:** Periodic page checks with diff detection (webhook on change)
- **Browser recording:** Record and replay browser interactions for debugging
- **Stealth mode:** Anti-detection measures (user-agent rotation, proxy rotation) for sites with aggressive bot detection

### 11.2 Known Limitations

- No persistent browser state between executions (by design for security)
- Cloudflare Browser Rendering Puppeteer API is a subset — some advanced CDP features unavailable
- 30-second max execution time per Worker invocation

---

## 12. Implementation Notes

### 12.1 Cloudflare Worker Architecture

```
MCPWorks API (FastAPI)
    │
    │ POST /v1/functions/{id}/execute
    │ (backend_type = "browser_rendering")
    │
    ▼
Cloudflare Worker (browser-rendering.mcpworks.io)
    │
    ├── Validates request (signed JWT from API)
    ├── Spawns Browser Rendering session
    ├── Executes navigation + extraction/screenshot
    ├── Uploads artifacts to R2 (if applicable)
    ├── Returns structured response
    │
    ▼
MCPWorks API
    │
    ├── Increments usage counter
    ├── Logs execution audit
    └── Returns response to AI assistant
```

### 12.2 Backend Registration

Browser Rendering joins the existing backend types:
- Code Sandbox
- Activepieces
- nanobot.ai
- GitHub Repo
- **Browser Rendering** (new)

### 12.3 Cloudflare Credits Impact

**Estimated cost per execution:**
- Browser Rendering: ~$0.01-0.02 per session
- R2 storage: negligible (small artifacts, TTL'd)
- Workers compute: included in Workers Paid (free via startup program)

**At 1,000 executions/month:** ~$10-20/month from credits
**Credits runway:** $5K credits supports ~250K-500K browser rendering executions

---

## 13. Spec Completeness Checklist

**Before moving to Plan phase:**

- [x] Clear user value proposition stated
- [x] Success criteria defined and measurable
- [x] All functional requirements enumerated
- [x] All constraints documented
- [x] Error scenarios identified
- [x] Security requirements specified
- [x] Performance requirements quantified
- [x] Token efficiency requirements stated
- [x] Testing requirements defined
- [x] Observability requirements defined
- [ ] Reviewed for Constitution compliance
- [ ] Logic checked (internally consistent)
- [ ] Peer reviewed (if team > 1)

---

## 14. Approval

**Status:** Conditionally Approved

**Approvals:**
- [x] CEO — Approved as A1 milestone (2026-03-06)
- [x] CFO — Approved with $1K credits cap (2026-03-06)
- [x] CPO — Approved after form submission moved to Phase 2 (2026-03-06)
- [ ] CTO — Pending Constitution compliance review
- [x] CLO — Approved, acceptable use policy required before A1 launch (2026-03-06)
- [x] CMO — Approved, second-wave announcement post developer preview (2026-03-06)

**Approved Date:** 2026-03-06 (conditional)
**Conditions for Full Approval:**
1. CTO completes Constitution compliance review
2. CLO delivers acceptable use policy addendum
**Next Review:** A1 implementation planning kickoff

---

## Changelog

**v0.2.0 (2026-03-06):**
- Board review: conditionally approved for A1
- Form submission and DOM interaction moved to Phase 2 (abuse risk, complexity)
- PDF generation moved to Phase 2
- Added $1K internal credits cap for browser rendering
- Added acceptable use policy requirement (CLO)
- Cloud metadata endpoint (169.254.169.254) added to blocked targets
- URL query param stripping made mandatory (not optional)
- Removed form input data references from Phase 1
- Second-wave marketing announcement planned (CMO)

**v0.1.0 (2026-03-06):**
- Initial draft
- Cloudflare Browser Rendering as new backend type for outbound web interactions
- Funded by Cloudflare for Startups credits ($5K)
