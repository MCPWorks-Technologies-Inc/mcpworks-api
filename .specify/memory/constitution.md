<!--
Sync Impact Report
==================
Version change: 0.0.0 → 1.0.0
Modified principles: Initial creation from docs/implementation/specs/CONSTITUTION.md
Added sections:
  - Core Principles (5 consolidated from original 10)
  - Quality Standards (Code, Docs, Performance, Security)
  - Development Workflow (Artifact flow, phase gates)
Removed sections: None (initial creation)
Templates requiring updates:
  - plan-template.md: ✅ Compatible (Constitution Check section present)
  - spec-template.md: ✅ Compatible (FR/NFR structure aligns with principles)
  - tasks-template.md: ✅ Compatible (Phase structure supports workflow)
Follow-up TODOs: None
-->

# mcpworks API Constitution

## Core Principles

### I. Spec-First Development

All implementation MUST begin with complete specifications following the artifact flow:
Constitution → Specification (WHAT) → Plan (HOW) → Tasks (WHO/WHEN) → Code.

- Specifications define requirements, constraints, user scenarios, and error handling
- Plans define technology choices, architecture, and deployment strategy
- Tasks MUST be 2-8 hours of work with clear acceptance criteria
- No code without an approved specification

**Rationale**: Detailed specs prevent costly rework and demonstrate production-ready engineering
discipline. Open-source contributors and enterprise customers expect clear specifications.

### II. Token Efficiency & Streaming

Every API response MUST be token-optimized; long-running operations MUST stream progress.

Token Efficiency:
- Target: 200-1000 tokens per operation (2-5x better than competitors)
- Return references, not full data (progressive disclosure)
- Implement semantic compression for errors and status messages

Streaming Architecture:
- Use Server-Sent Events (SSE) for real-time updates on deployments, provisioning
- Provide immediate feedback (queued → in_progress → complete)
- Enable AI assistants to show users live progress

**Rationale**: Token efficiency = competitive moat. MCPs that burn 5000 tokens/operation
won't scale. Real-time streaming = 12-18 month technical lead over batch/polling competitors.

### III. Transaction Safety & Security

Multi-step operations MUST be atomic with automatic rollback; every feature MUST be secure
from day one.

Transaction Safety:
- Hold credits before operation starts
- Commit credits only on success
- Release/refund credits on failure
- Implement compensation logic for partial failures

Security by Default:
- Port restrictions enforced (25, 445 blocked; 22 requires approval)
- Rate limiting per customer
- Encryption at rest and in transit
- Input validation and sanitization on all endpoints

**Rationale**: Bank-grade transaction safety = enterprise trust. No double-charging, no
orphaned resources. Security incidents destroy customer trust; SOC 2 compliance starts at
architecture, not retrofitted later.

### IV. Provider Abstraction & Observability

Backend infrastructure MUST be swappable; every operation MUST be traceable and debuggable.

Provider Abstraction:
- Abstract all provider-specific code behind interfaces
- Start with DigitalOcean (Phase 1), support multi-provider (Phase 2+)
- Enable self-hosting on any infrastructure

Observable by Design:
- Structured logging (JSON, searchable)
- Distributed tracing (operation IDs across services)
- Metrics collection (Prometheus-compatible)
- Customer-facing audit logs

**Rationale**: Infrastructure flexibility means self-hosters and enterprise customers can deploy
on their preferred cloud. Production incidents will happen; observability = fast resolution = customer retention.

### V. API Contracts & Test Coverage

MCP tool signatures are contracts, not suggestions; all business logic MUST have automated tests.

API Contracts:
- Semantic versioning for breaking changes
- Backward compatibility for 12 months minimum
- Deprecation warnings 6 months in advance
- Clear migration paths documented

Test Coverage Requirements:
- Unit tests: 80% coverage for business logic
- Integration tests: Critical paths (provision → deploy → monitor)
- E2E tests: Full customer workflows
- Load tests: 100 concurrent operations minimum

**Rationale**: AI assistants cache tool schemas; breaking changes = angry developers = churn.
Enterprise customers and community contributors expect well-tested code; <80% = quality risk.

## Quality Standards

### Code Quality

- **Formatting**: Black formatting, isort imports
- **Type Safety**: mypy strict mode; all functions MUST have type hints
- **Linting**: flake8 + pylint; maximum cyclomatic complexity = 10 per function
- **Docstrings**: All public functions MUST have docstrings

### Documentation Quality

- **Modules**: Every module has README explaining purpose
- **API Docs**: OpenAPI 3.0 spec for all REST endpoints
- **MCP Docs**: Tool descriptions <20 tokens, comprehensive examples
- **Runbooks**: All operational procedures documented

### Performance Standards

- **API Response Time**: p95 < 500ms (excluding long-running ops)
- **MCP Tool Response**: p95 < 200 tokens
- **Deployment Speed**: <5 minutes for standard Node.js app
- **Uptime**: 99.9% target (Phase 2+)

### Security Standards

- **Authentication**: JWT with 1-hour expiry, refresh tokens
- **Authorization**: RBAC with principle of least privilege
- **Secrets**: NEVER in code, always in environment/vault
- **Dependencies**: Automated vulnerability scanning (Dependabot/Snyk)

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
- Spec is complete per spec-template.md checklist
- Spec has been reviewed for internal consistency
- Spec addresses all Constitution principles

**Cannot proceed to Tasks until:**
- Plan is complete per plan-template.md checklist
- Plan maps to all spec requirements
- Plan has been reviewed for security/performance
- Constitution Check section passes

**Cannot proceed to Implementation until:**
- All prerequisite tasks are complete
- Task acceptance criteria are clear
- Test strategy is defined

### Production Readiness

All specifications MUST be written assuming:
- Open-source contributors will review and extend the code
- Enterprise customers need to understand architecture in <2 hours
- Partners want evidence of engineering rigor

**Acceptable Technical Debt:**
- Temporary workarounds with documented mitigation plan
- Phase 1 single-provider implementation
- Manual processes with automation roadmap

**Unacceptable:**
- Security vulnerabilities
- Data loss risks
- Unmonitored production issues
- Undocumented system behavior

## Governance

This Constitution is the supreme authority for mcpworks API development. All specifications,
plans, tasks, and implementations MUST comply with these principles.

### Amendment Process

This Constitution may be amended when:
- Business strategy changes materially
- New technical constraints emerge
- Team size changes significantly

**Amendment requires:**
- Written rationale for change
- Impact analysis on existing specs
- Version increment following semantic versioning:
  - MAJOR: Backward-incompatible principle changes
  - MINOR: New principle or section added
  - PATCH: Clarifications and wording improvements

### Compliance Review

- All PRs MUST verify Constitution compliance
- Complexity MUST be justified in plan.md Complexity Tracking section
- Use CLAUDE.md for runtime development guidance

### References

- Source: docs/implementation/specs/CONSTITUTION.md (original v1.0)
- Token Optimization: docs/implementation/guidance/mcp-token-optimization.md
- Technical Architecture: docs/implementation/plans/technical-architecture.md

**Version**: 1.0.0 | **Ratified**: 2025-10-30 | **Last Amended**: 2025-12-16
