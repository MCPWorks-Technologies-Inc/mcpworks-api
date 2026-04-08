# Spec-Driven Development Workflow

This project follows **spec-kit methodology** — all code must have an approved specification first.

## Workflow

```
Constitution → Specification → Plan → Tasks → Implementation
```

## Before Writing Any Code

1. Read [docs/implementation/specs/CONSTITUTION.md](../implementation/specs/CONSTITUTION.md)
2. Check if specification exists in [docs/implementation/specs/](../implementation/specs/)
3. If no spec, create one using [TEMPLATE.md](../implementation/specs/TEMPLATE.md)
4. Get spec reviewed and approved
5. Create implementation plan in [docs/implementation/plans/](../implementation/plans/)
6. Break into atomic tasks
7. Then write code

## Key Principles from Constitution

- **Spec-first development:** No code without approved specification
- **Token efficiency first:** Target 200-1000 tokens/operation (2-5x better than AWS/GCP)
- **Streaming architecture:** Use SSE for long-running operations
- **Usage limit safety:** Check subscription limits before execution, increment on success
- **Provider abstraction:** Workflow execution layer must be swappable
- **Security by default:** Rate limiting, input validation, subscription enforcement
- **Transparent pricing:** Subscription tiers and usage exposed to LLM for intelligent decisions
- **Observable by design:** Structured logging, metrics, tracing
