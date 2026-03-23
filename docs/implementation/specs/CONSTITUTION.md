# mcpworks API Project Constitution

**Version:** 1.1
**Created:** 2025-10-30
**Updated:** 2025-12-16
**Purpose:** Governing principles for mcpworks API development

---

## Project Mission

Build the open-source standard for token-efficient AI agents. MCPWorks is a namespace-based function hosting platform where AI assistants create and execute functions via MCP over HTTPS. Agents run autonomously with scheduling, state, and BYOAI orchestration.

**Core Value Proposition:** Describe the automation. Your AI builds it. MCPWorks runs it. Open-source (BSL 1.1) — self-host or use MCPWorks Cloud.

---

## Development Principles

### 1. Spec-First Development

**All implementation begins with complete specifications.**

- Write specifications defining WHAT (requirements, constraints, user scenarios)
- Write plans defining HOW (technical approach, architecture, trade-offs)
- Write tasks defining WHO/WHEN (actionable breakdown, dependencies)
- Only then write implementation code

**Rationale:** Detailed specs prevent costly rework and demonstrate production-ready engineering discipline. Open-source contributors and enterprise customers expect clear specifications.

### 2. Token Efficiency First

**Every API response must be token-optimized.**

- Target: 200-1000 tokens per operation (2-5x better than competitors)
- Return references, not full data
- Implement progressive disclosure
- Stream large responses via SSE

**Rationale:** Token efficiency = competitive moat. MCPs that burn 5000 tokens/operation won't scale.

### 3. Streaming Architecture

**Long-running operations must stream progress, not batch.**

- Use Server-Sent Events (SSE) for real-time updates
- Provide immediate feedback (deployment queued → installing deps → deployed)
- Enable AI to show users live progress

**Rationale:** Real-time streaming = 12-18 month technical lead over competitors who will use batch/polling.

### 4. Transaction Safety

**Multi-step operations must be atomic with automatic rollback.**

- Check usage limits before operation starts
- Increment usage only on success
- Implement compensation logic for partial failures
- No orphaned resources on failure

**Rationale:** Bank-grade transaction safety = enterprise trust. No orphaned resources, clean rollback on failure.

### 5. Provider Abstraction

**Backend infrastructure must be swappable.**

- Abstract all provider-specific code behind interfaces
- Start with DigitalOcean (Phase 1)
- Support multi-provider (Phase 2+)
- Enable community self-hosting on any infrastructure (Phase 3)

**Rationale:** Infrastructure flexibility. Self-hosters choose their cloud. Enterprise customers choose their provider. No vendor lock-in.

### 6. Security by Default

**Every feature must be secure from day one.**

- Port restrictions (25, 445 blocked; 22 requires approval)
- Rate limiting per customer
- Monitoring and abuse detection
- Encryption at rest and in transit

**Rationale:** Security incidents destroy customer trust. SOC 2 compliance starts at architecture, not retrofitted later.

### 7. Transparent Pricing

**Usage limits and subscription tiers must be real-time accessible to AI.**

- Expose tier limits via MCP resources
- Allow AI to check remaining executions
- Show usage percentage during operations
- Warn when approaching tier limits

**Rationale:** AI-native usage transparency = unique value proposition. LLMs can reason about usage limits in real-time.

### 8. Observable by Design

**Every operation must be traceable and debuggable.**

- Structured logging (JSON, searchable)
- Distributed tracing (operation IDs across services)
- Metrics collection (Prometheus-compatible)
- Customer-facing audit logs

**Rationale:** Production incidents will happen. Observability = fast resolution = customer retention.

### 9. API Contracts

**MCP tool signatures are contracts, not suggestions.**

- Semantic versioning for breaking changes
- Backward compatibility for 12 months
- Deprecation warnings 6 months in advance
- Clear migration paths

**Rationale:** AI assistants cache tool schemas. Breaking changes = angry developers = churn.

### 10. Test Coverage Requirements

**All business logic must have automated tests.**

Minimum coverage:
- Unit tests: 80% coverage for business logic
- Integration tests: Critical paths (provision → deploy → monitor)
- E2E tests: Full customer workflows
- Load tests: 100 concurrent operations

**Rationale:** Enterprise customers and community contributors expect well-tested code. <80% coverage = quality risk.

---

## Quality Standards

### Code Quality

- **Python:** Black formatting, mypy type checking, flake8 linting
- **Type Safety:** All functions must have type hints
- **Docstrings:** All public functions must have docstrings
- **Complexity:** Maximum cyclomatic complexity = 10 per function

### Documentation Quality

- **README:** Every module has README explaining purpose
- **API Docs:** OpenAPI 3.0 spec for all REST endpoints
- **MCP Docs:** Tool descriptions <20 tokens, comprehensive examples
- **Runbooks:** All operational procedures documented

### Performance Standards

- **API Response Time:** p95 < 500ms (excluding long-running ops)
- **MCP Tool Response:** p95 < 200 tokens
- **Deployment Speed:** <5 minutes for standard Node.js app
- **Uptime:** 99.9% target (not guaranteed until Phase 2)

### Security Standards

- **Authentication:** JWT with 1-hour expiry, refresh tokens
- **Authorization:** RBAC with principle of least privilege
- **Secrets:** Never in code, always in environment/vault
- **Dependencies:** Automated vulnerability scanning (Dependabot)

---

## Specification Standards

### What Belongs in a Spec

**Include:**
- User scenarios and workflows
- Functional requirements ("must allow X")
- Non-functional requirements (performance, security)
- Constraints and guardrails
- Error handling expectations
- Edge cases and failure modes

**Exclude:**
- Technology choices (goes in Plan)
- Implementation details (goes in Implementation)
- Code snippets (unless illustrating requirement)

### Spec Completeness Checklist

Before marking spec as "Ready for Planning":

- [ ] Clear user value proposition stated
- [ ] Success criteria defined and measurable
- [ ] All functional requirements enumerated
- [ ] All constraints documented
- [ ] Error scenarios identified
- [ ] Security requirements specified
- [ ] Performance requirements quantified
- [ ] Token efficiency requirements stated
- [ ] Reviewed by at least one other person (if team >1)

### Spec Review Process

1. **Draft:** Author writes initial spec
2. **Logic Check:** Author reviews for internal consistency
3. **Peer Review:** Another engineer reviews (if available)
4. **Stakeholder Review:** Business/product reviews value proposition
5. **Approved:** Spec frozen, ready for Plan phase

---

## Plan Standards

### What Belongs in a Plan

**Include:**
- Technology stack choices (with rationale)
- Architecture diagrams
- Database schema design
- API endpoint design
- Third-party integrations
- Deployment strategy
- Rollback procedures

**Exclude:**
- Detailed code (goes in Implementation)
- User scenarios (already in Spec)

### Plan Completeness Checklist

Before marking plan as "Ready for Tasks":

- [ ] All spec requirements mapped to technical approach
- [ ] Architecture diagram created
- [ ] Database schema designed
- [ ] API contracts defined
- [ ] Error handling strategy documented
- [ ] Testing strategy defined
- [ ] Deployment strategy documented
- [ ] Rollback procedure defined
- [ ] Security review completed
- [ ] Token efficiency analysis completed

---

## Task Standards

### Task Breakdown Principles

- Tasks should be 2-8 hours of work
- Tasks must have clear acceptance criteria
- Tasks must specify dependencies
- Tasks must be assignable to one person

### Task Template

```markdown
## Task: [Verb] [Noun] [Context]

**Spec:** [Link to spec]
**Plan:** [Link to plan]
**Estimated Effort:** [2-8 hours]
**Dependencies:** [List of prerequisite tasks]

### Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Tests written and passing
- [ ] Documentation updated

### Implementation Notes
[Any important context for implementer]
```

---

## Development Workflow

### Artifact Flow

```
Constitution (this doc)
    ↓
Specification (WHAT we're building)
    ↓
Plan (HOW we'll build it)
    ↓
Tasks (WHO does WHAT WHEN)
    ↓
Implementation (CODE)
```

### Phase Gates

**Cannot proceed to Plan until:**
- Spec is complete per checklist
- Spec has been reviewed
- Spec addresses all Constitution principles

**Cannot proceed to Tasks until:**
- Plan is complete per checklist
- Plan maps to all spec requirements
- Plan has been reviewed for security/performance

**Cannot proceed to Implementation until:**
- All prerequisite tasks are complete
- Task acceptance criteria are clear
- Test strategy is defined

---

## Production Readiness Principles

### Community-Ready Documentation

All specifications must be written assuming:
- Open-source contributors will review and extend the code
- Enterprise customers need to understand architecture in <2 hours
- Partners want evidence of engineering rigor

### Technical Debt Management

**Acceptable:**
- Temporary workarounds with documented mitigation plan
- Phase 1 single-provider implementation
- Manual processes with automation roadmap

**Unacceptable:**
- Security vulnerabilities
- Data loss risks
- Unmonitored production issues
- Undocumented system behavior

---

## Amendment Process

This Constitution may be amended when:
- Business strategy changes materially
- New technical constraints emerge
- Team size changes significantly (solo → team)

**Amendment requires:**
- Written rationale for change
- Impact analysis on existing specs
- Approval from CTO (Simon)

---

## References

- [Spec-Kit Methodology](https://github.com/github/spec-kit)
- [mcpworks API Spec](../../../SPEC.md)
- [Technical Architecture](../plans/technical-architecture.md)
- [Token Optimization](../guidance/mcp-token-optimization.md)

---

**Approved by:** Simon Carr (CTO)
**Date:** 2025-10-30
**Next Review:** 2025-12-30 (every 60 days)
