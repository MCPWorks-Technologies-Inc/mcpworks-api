# mcpworks API Specification Framework

**Version:** 1.1
**Created:** 2025-10-30
**Updated:** 2025-12-16
**Purpose:** Guide for using spec-driven development in mcpworks API

---

## Overview

This directory contains the specification framework for mcpworks API development. Following the [spec-kit methodology](https://github.com/github/spec-kit), we use a five-artifact approach to software development:

```
Constitution (governing principles)
    ↓
Specification (WHAT we're building, WHY)
    ↓
Plan (HOW we'll build it)
    ↓
Tasks (WHO does WHAT WHEN)
    ↓
Implementation (CODE)
```

**Core Principle:** No code is written until specifications are complete and reviewed.

**Why:** Detailed specs prevent costly rework and demonstrate production-ready engineering discipline. Open-source contributors and enterprise customers expect clear specifications.

---

## Quick Start

### 1. Read the Constitution First

Start by reading [CONSTITUTION.md](./CONSTITUTION.md) to understand:
- 10 development principles (spec-first, token efficiency, streaming, etc.)
- Quality standards (code, documentation, performance, security)
- Spec completeness requirements
- Phase gate requirements

**Every spec must comply with the Constitution.**

### 2. Use the Template

Copy [TEMPLATE.md](./TEMPLATE.md) when starting a new specification:

```bash
cp docs/implementation/specs/TEMPLATE.md docs/implementation/specs/my-feature-spec.md
```

### 3. Follow the Workflow

```
Draft → Logic Check → Review → Approved → Plan Phase
```

---

## When to Create a Spec

### Always Create a Spec For:

- **New MCP tools** (e.g., provision_service, deploy_application)
- **Core system components** (e.g., usage tracking, billing engine)
- **Third-party integrations** (e.g., Stripe, DigitalOcean API)
- **Security-critical features** (e.g., authentication, authorization)
- **User-facing workflows** (e.g., onboarding, dashboard)

### Do NOT Create a Spec For:

- Bug fixes (unless they require architectural changes)
- Documentation updates
- Test additions
- Refactoring without behavior changes
- Configuration changes

### Rule of Thumb:

If the work takes >2 days or impacts multiple components, write a spec.

---

## Specification Workflow

### Phase 1: Draft (Author)

1. Copy TEMPLATE.md
2. Fill in all 13 sections:
   - Overview (purpose, value, success criteria, scope)
   - User Scenarios (primary and secondary workflows)
   - Functional Requirements (with priorities)
   - Non-Functional Requirements (performance, security, reliability)
   - Constraints & Assumptions
   - Error Scenarios & Edge Cases
   - Token Efficiency Analysis
   - Security Analysis
   - Observability Requirements
   - Testing Requirements
   - Future Considerations
   - Spec Completeness Checklist
   - Approval section

3. Mark status as **"Draft"**

### Phase 2: Logic Check (Author)

Review your own spec for:
- **Internal consistency:** Do requirements contradict each other?
- **Completeness:** Are all edge cases covered?
- **Clarity:** Can someone else understand this without asking questions?
- **Constitution compliance:** Does this follow all 10 development principles?

Run through the Spec Completeness Checklist (Section 12).

Mark status as **"Logic Check"** when ready.

### Phase 3: Review (Peer/Stakeholder)

- **Solo founder (Phase 1):** Self-review with fresh eyes (24-hour wait)
- **Team (Phase 2+):** Another engineer reviews
- **Stakeholder review:** Business/product reviews value proposition

Reviewers check:
- User value is clear and compelling
- Requirements are testable
- Security and performance standards met
- Token efficiency requirements stated
- Constitution compliance

Mark status as **"Review"** while under review.

### Phase 4: Approved

- CTO (Simon) approves all specs
- CEO approves if business impact
- Security review required if sensitive data/operations

Mark status as **"Approved"** with approval date.

**Spec is now frozen.** Changes require new version.

### Phase 5: Move to Plan

Once approved, create Plan document:

```bash
cp docs/implementation/specs/TEMPLATE.md docs/implementation/plans/my-feature-plan.md
```

Plan addresses HOW:
- Technology stack choices (with rationale)
- Architecture diagrams
- Database schema
- API endpoint design
- Deployment strategy
- Rollback procedures

---

## Example Specifications

### Example 1: MCP Service Provisioning Tool

**File:** `service-provisioning-spec.md`

**Covers:**
- User scenario: AI assistant provisions Node.js hosting
- Requirements: Create droplet, configure firewall, install Node.js, setup monitoring
- Token efficiency: Return service_id + stream_url (not full logs)
- Security: Port restrictions (25, 445 blocked; 22 requires approval)
- Error handling: Rollback on failure, no usage counted

**Status:** Ready to write after A0 completion

### Example 2: Usage Tracking System

**File:** `usage-tracking-spec.md`

**Covers:**
- User scenario: Track execution count against subscription tier limits
- Requirements: Check limit before execution, increment on success
- Token efficiency: Simple status responses ("within_limit", "limit_exceeded")
- Security: Prevent abuse, audit logging
- Error handling: Graceful handling when limit reached

**Status:** Critical for MVP

### Example 3: Deployment Progress Streaming

**File:** `deployment-streaming-spec.md`

**Covers:**
- User scenario: AI assistant shows real-time deployment progress
- Requirements: Server-Sent Events (SSE) for live updates
- Token efficiency: <50 tokens per update, stage indicators
- Performance: p95 latency <200ms per event
- Error handling: Connection recovery, error event format

**Status:** Competitive advantage (12-18 month lead)

---

## Spec Naming Conventions

### Format:

```
[component]-[feature]-spec.md
```

### Examples:

- `mcp-service-provisioning-spec.md` - MCP tool for provisioning services
- `billing-usage-tracking-spec.md` - Usage tracking and limits system
- `api-deployment-streaming-spec.md` - SSE streaming for deployments
- `integration-stripe-connect-spec.md` - Stripe Connect integration
- `security-rate-limiting-spec.md` - Rate limiting implementation
- `auth-jwt-session-spec.md` - JWT authentication system

### Versioning:

Use version numbers in the spec header, not filenames:
- `**Version:** 1.0.0` (initial approved)
- `**Version:** 1.1.0` (minor changes)
- `**Version:** 2.0.0` (breaking changes)

Archive superseded specs in `docs/archive/specs/`.

---

## Quality Standards

### Spec Length

- **Minimum:** 200 lines (comprehensive coverage)
- **Typical:** 300-500 lines (well-documented)
- **Maximum:** 1000 lines (split into multiple specs if larger)

### Token Efficiency Requirements

Every spec must include Section 7: Token Efficiency Analysis:

```markdown
## 7. Token Efficiency Analysis

### 7.1 Tool Definitions
**Estimated tokens for tool schemas:** X tokens total

### 7.2 Typical Responses
**Operation:** Do X
**Response Size:** Y tokens (summary) | Z tokens (detailed)
**Optimization Strategy:** [How we keep it small]

### 7.3 Worst Case
**Largest possible response:** X tokens
**Mitigation:** Pagination, streaming, compression
```

**Target:** 200-1000 tokens per operation (2-5x better than AWS/GCP MCPs)

### Security Requirements

Every spec must include Section 8: Security Analysis:

```markdown
## 8. Security Analysis

### 8.1 Threat Model
**Threat:** Attacker does X
**Impact:** [Confidentiality | Integrity | Availability]
**Mitigation:** We prevent this by Y
**Residual Risk:** [Low | Medium | High]

### 8.2 PII/Sensitive Data
**What sensitive data is involved:**
- Data type 1: How it's protected

### 8.3 Compliance
**Relevant regulations:**
- PIPEDA (Canada): Requirement X
- GDPR (if EU customers): Requirement Y
```

### Performance Requirements

Every spec must quantify performance expectations:

```markdown
## 4.1 Performance
- **Response Time:** p95 < X ms for operation Y
- **Throughput:** Must handle X operations/second
- **Token Efficiency:** Average response < X tokens
```

---

## Completeness Checklist

Before marking spec as "Ready for Planning":

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

**All boxes must be checked before approval.**

---

## Phase Gates

### Cannot Proceed to Plan Until:

- Spec is complete per checklist
- Spec has been reviewed
- Spec addresses all Constitution principles
- Spec is approved by CTO (Simon)

### Cannot Proceed to Tasks Until:

- Plan is complete per checklist
- Plan maps to all spec requirements
- Plan has been reviewed for security/performance
- Plan is approved by CTO (Simon)

### Cannot Proceed to Implementation Until:

- All prerequisite tasks are complete
- Task acceptance criteria are clear
- Test strategy is defined
- Implementation branch created

**No exceptions.** Phase gates prevent costly rework.

---

## Common Mistakes to Avoid

### 1. Skipping User Scenarios

**Bad:** "Build a service provisioning API"
**Good:** "As an AI assistant, I need to provision a Node.js hosting environment so that I can deploy my user's web application without manual DevOps work."

User scenarios clarify intent and success criteria.

### 2. Vague Requirements

**Bad:** "System must be fast"
**Good:** "p95 API response time < 500ms for all MCP tool calls (excluding long-running operations like deployments)"

Quantify everything.

### 3. Implementation in Spec

**Bad:** "Use PostgreSQL for storage with SQLAlchemy ORM"
**Good:** "System must persist deployment state with ACID guarantees"

Technology choices go in Plan, not Spec.

### 4. Missing Error Scenarios

**Bad:** Only documenting happy path
**Good:** Document what happens when DigitalOcean API is down, usage limit exceeded, invalid configuration, timeout occurs, etc.

Errors are not edge cases—they're normal operation.

### 5. Token Efficiency Afterthought

**Bad:** "We'll optimize tokens later"
**Good:** "Tool returns service_id and stream_url (20 tokens) instead of full deployment logs (5000 tokens)"

Token efficiency is core architecture, not optimization.

---

## Tools and Resources

### Required Reading

- [CONSTITUTION.md](./CONSTITUTION.md) - Governing principles
- [TEMPLATE.md](./TEMPLATE.md) - Specification template
- [mcp-token-optimization.md](../guidance/mcp-token-optimization.md) - Token efficiency patterns
- [Spec-Kit Methodology](https://github.com/github/spec-kit) - Original framework

### Recommended Reading

- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/) - Official MCP docs
- [SPEC.md](../../../SPEC.md) - Main API specification (workflow platform)
- [technical-architecture.md](../plans/technical-architecture.md) - System architecture

### Token Estimation

Use `tiktoken` library for accurate token counts:

```python
import tiktoken

def estimate_tokens(text, model="gpt-4"):
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

# Example
tool_response = {"service_id": "srv_abc123", "status": "running"}
tokens = estimate_tokens(str(tool_response))
print(f"Response uses {tokens} tokens")
```

---

## FAQ

### Q: Do I need a spec for every GitHub Issue?

**A:** No. Only for issues that involve new features, architecture changes, or multi-component work. Bug fixes and simple tasks can skip directly to implementation.

### Q: How long should spec writing take?

**A:** Budget 2-8 hours for a comprehensive spec. Complex systems (billing, security) may take longer. If taking >1 day, break into multiple specs.

### Q: What if requirements change during implementation?

**A:** Minor clarifications can be added as comments. Major changes require spec update and re-approval. Version the spec accordingly.

### Q: Can I start coding while spec is in review?

**A:** No. Phase gates are strict. Use review time to research technologies, read docs, or write prototypes (not production code).

### Q: How do I handle uncertainty in specs?

**A:** Document assumptions explicitly in Section 5. Flag high-risk assumptions and plan validation experiments before full implementation.

### Q: Solo founder: Do I really need to review my own specs?

**A:** Yes. Wait 24 hours, then re-read with fresh eyes. Ask: "If I hired someone tomorrow, could they build this from my spec alone?"

---

## Version History

**v1.0 (2025-10-30):**
- Initial framework documentation
- Usage guide and workflow
- Example specifications
- Quality standards and checklists
- FAQ and common mistakes

---

## Next Steps

1. **Read CONSTITUTION.md** to understand development principles
2. **Review TEMPLATE.md** to see spec structure
3. **Create your first spec** for a core mcpworks component
4. **Follow the workflow** (Draft → Logic Check → Review → Approved)
5. **Move to Plan phase** after approval

Questions? See CLAUDE.md in repository root or consult with CTO (Simon Carr).
