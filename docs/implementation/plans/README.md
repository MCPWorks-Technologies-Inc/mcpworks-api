# Implementation Plans

**Purpose:** This directory contains Plan documents that describe HOW we will build mcpworks Infrastructure MCP components.

---

## What Belongs Here

**Plans describe technical implementation strategies:**
- Technology stack choices with rationale
- Architecture diagrams and component designs
- Database schema designs
- API endpoint designs
- Third-party integration approaches
- Deployment strategies
- Rollback procedures
- Performance optimization plans

**Plans answer questions like:**
- Which technologies/frameworks will we use?
- How will components communicate?
- What's the database structure?
- How do we handle failures?
- What's the deployment pipeline?

---

## Relationship to Other Artifacts

```
Constitution (governing principles)
    ↓
Specification (WHAT we're building, WHY) ← in specs/
    ↓
Plan (HOW we'll build it) ← YOU ARE HERE
    ↓
Tasks (WHO does WHAT WHEN)
    ↓
Implementation (CODE)
```

**Plans are created AFTER specifications are approved.**

---

## Plan Standards

### Before Creating a Plan

**Prerequisites:**
- Corresponding specification exists in `../specs/` directory
- Specification has been reviewed and approved
- Specification completeness checklist is complete

### Plan Completeness Checklist

From CONSTITUTION.md, before marking plan as "Ready for Tasks":

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

### Plan Template Structure

```markdown
# [Component] - Implementation Plan

**Version:** 1.0.0
**Spec:** [Link to specification in ../specs/]
**Status:** Draft | Review | Approved
**Plan Author:** [Name]

## 1. Technology Stack

- Framework: [Choice with rationale]
- Database: [Choice with rationale]
- Libraries: [Key dependencies with rationale]

## 2. Architecture

[Architecture diagram]
[Component descriptions]

## 3. Database Schema

[Tables, relationships, indexes]

## 4. API Design

[Endpoints, request/response formats]

## 5. Error Handling Strategy

[How errors are detected, reported, handled]

## 6. Testing Strategy

[Unit, integration, E2E test approach]

## 7. Deployment Strategy

[How to deploy, rollback, monitor]

## 8. Performance Considerations

[Bottlenecks, optimizations, scaling]

## 9. Security Considerations

[Auth, encryption, audit logging]

## 10. Token Efficiency Implementation

[How to achieve token targets from spec]
```

---

## Current Plans

| Plan | Version | Status | Spec | Description |
|------|---------|--------|------|-------------|
| `technical-architecture.md` | 2.0 | Active | `../specs/mcpworks-mcp-server-spec.md` | **PRIMARY PLAN** System architecture for mcpworks Infrastructure MCP server: technology stack (Python/FastAPI), 19 MCP tools, provider abstraction layer, SSE streaming, subscription billing, deployment flows, scalability design (1K→10K→100K customers), disaster recovery, acquirer technical fit analysis. |
| `provider-selection-strategy.md` | 1.0 | Active | (Provider integration section of main spec) | Provider selection and integration strategy: domain registration (OpenSRS), DNS (Cloudflare), SSL (Let's Encrypt/Sectigo), hosting (DigitalOcean/Hetzner/OVH), email (Zoho/Postmark), payments (Stripe), SaaS integrations. Includes pricing analysis, margin calculations (79% achievable), API quality assessment, phased implementation roadmap (A0→A1→A2→A3). |

---

## Phase Gates

**Cannot Proceed to Tasks Until:**
- Plan is complete per checklist above
- Plan maps to all spec requirements
- Plan has been reviewed for security/performance
- Plan is approved by CTO (Simon)

**Cannot Proceed to Implementation Until:**
- All prerequisite tasks are complete
- Task acceptance criteria are clear
- Test strategy is defined
- Implementation branch created

---

## Common Mistakes to Avoid

### 1. Premature Planning

**Bad:** Writing plans before spec is approved
**Good:** Wait for spec approval, then create plan

Plans depend on approved requirements. Spec changes invalidate plans.

### 2. Including Requirements in Plans

**Bad:** "System must support 100 concurrent users"
**Good:** "Architecture uses load balancer + 3 app servers to handle 100 concurrent users"

Requirements go in specs, technical approaches go in plans.

### 3. Skipping Architecture Diagrams

**Bad:** Text-only component descriptions
**Good:** Visual diagrams + text descriptions

Diagrams make architecture reviews faster and clearer.

### 4. Vague Technology Choices

**Bad:** "We'll use a database"
**Good:** "PostgreSQL 15 chosen for ACID compliance, JSON support, and mature ORMs (SQLAlchemy)"

Include rationale for every technology choice.

---

## References

- [CONSTITUTION.md](../specs/CONSTITUTION.md) - Plan standards and completeness checklist
- [Spec Directory](../specs/) - Specifications that plans implement
- [Guidance Directory](../guidance/) - Implementation patterns and best practices
