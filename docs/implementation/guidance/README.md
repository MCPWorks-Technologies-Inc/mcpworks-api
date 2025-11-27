# Implementation Guidance

**Purpose:** This directory contains implementation patterns, best practices, and technical guidance documents that inform HOW we write code.

---

## What Belongs Here

**Guidance documents provide patterns and best practices:**
- Code patterns and anti-patterns
- Performance optimization techniques
- Security best practices
- Testing strategies
- Common pitfalls and solutions
- Library usage examples
- Architectural patterns
- Debugging techniques

**Guidance answers questions like:**
- What's the best way to implement X?
- How do I optimize for performance/tokens/security?
- What patterns should I follow?
- What mistakes should I avoid?
- How do other components solve similar problems?

---

## Relationship to Other Artifacts

```
Constitution (governing principles) ← Establishes standards
    ↓
Specification (WHAT we're building, WHY)
    ↓
Plan (HOW we'll build it)
    ↓
Guidance (BEST PRACTICES for implementation) ← YOU ARE HERE
    ↓
Tasks (WHO does WHAT WHEN)
    ↓
Implementation (CODE) ← Applies guidance patterns
```

**Guidance documents are living references** that evolve as we learn what works and what doesn't.

---

## Guidance vs. Plans vs. Specs

### Specification (Spec)
- **Describes:** WHAT and WHY
- **Example:** "System must stream deployment logs via SSE with <50 tokens per event"
- **Location:** `../specs/`

### Plan
- **Describes:** HOW (architecture and strategy)
- **Example:** "Use FastAPI StreamingResponse with asyncio generators for SSE implementation"
- **Location:** `../plans/`

### Guidance
- **Describes:** BEST PRACTICES for implementation
- **Example:** "SSE Pattern: Always set Cache-Control: no-cache, yield every 500ms to keep connection alive, handle client disconnects gracefully"
- **Location:** `../guidance/` (here)

---

## Guidance Document Standards

### Document Structure

```markdown
# [Topic] - Implementation Guidance

**Version:** 1.0
**Created:** YYYY-MM-DD
**Status:** Active | Draft | Deprecated
**Related Specs:** [Links to specs that use these patterns]

## Overview

[What this guidance covers and why it matters]

## Key Principles

[Core principles to follow]

## Patterns

### Pattern 1: [Name]

**Problem:** [What problem does this solve?]
**Solution:** [How to implement]
**Example:** [Code example]
**Rationale:** [Why this is the best approach]

### Pattern 2: [Name]

[Repeat structure]

## Anti-Patterns

### Anti-Pattern 1: [Name]

**Problem:** [What's wrong with this approach?]
**Why It's Bad:** [Consequences]
**Instead, Do This:** [Correct approach]

## Common Mistakes

[List of frequent errors and how to avoid them]

## Tools & Libraries

[Recommended tools for implementing these patterns]

## References

[External resources, RFCs, documentation]
```

### When to Create Guidance

Create guidance documents when:
- You discover a pattern that works well (share it)
- Multiple components need the same pattern (avoid duplication)
- You encounter a subtle bug that others should avoid
- There's a non-obvious way to do something correctly
- Performance/security requires specific techniques
- Constitution principles need elaboration

### When NOT to Create Guidance

Don't create guidance for:
- One-off implementation details (put in code comments)
- Spec requirements (those go in specs)
- Architecture decisions (those go in plans)
- Obvious/trivial patterns (don't document the obvious)

---

## Current Guidance Documents

| Document | Version | Status | Topics Covered |
|----------|---------|--------|----------------|
| `mcp-token-optimization.md` | 1.0 | Active | **CRITICAL** Production MCP token efficiency patterns: smart tool definitions (progressive disclosure, <20 tokens per description), response compression (references not full data, abbreviated keys), caching & state management (conversation-aware, incremental updates), semantic compression (flatten structures, limit arrays), zoom levels (summary/standard/detailed/full), batch operations (single call vs multiple round trips), two-tier architecture (lightweight + heavy MCP), streaming patterns (SSE, credit transparency), specialized compression models. Target: 200-1000 tokens/operation (2-5x more efficient than AWS/GCP MCPs). Includes mcpworks-specific examples: deployment streaming, credit burn summaries, integration status compression. |

---

## How to Use Guidance

### During Planning

- Review relevant guidance when creating plans
- Reference guidance documents in plan's "Implementation Notes"
- Identify gaps in guidance (create new docs as needed)

### During Implementation

- Consult guidance before starting new code
- Apply patterns consistently across codebase
- Update guidance when you discover better patterns
- Flag anti-patterns in code reviews

### During Code Review

- Check that code follows guidance patterns
- Suggest guidance documents to reviewers
- Propose new guidance if patterns emerge

---

## Contributing to Guidance

### Adding New Guidance

1. Identify a pattern worth sharing
2. Create document following template above
3. Include code examples
4. Link to related specs/plans
5. Review with team (if team > 1)
6. Update this README to list new document

### Updating Existing Guidance

1. Identify improvement or correction
2. Update document with version bump
3. Add changelog entry
4. Notify team of significant changes (if team > 1)

### Deprecating Guidance

1. Mark document status as "Deprecated"
2. Add note explaining why deprecated
3. Link to replacement guidance (if applicable)
4. Move to `deprecated/` subdirectory after 6 months

---

## Guidance Philosophy

From CONSTITUTION.md:

> "Guidance documents capture lessons learned and best practices. They are living documents that evolve as we learn what works. Good guidance prevents repeating mistakes and accelerates development."

**Key principles:**
- **Practical over theoretical:** Real code examples, not academic discussions
- **Opinionated:** Recommend specific approaches, explain trade-offs
- **Maintained:** Update as we learn, deprecate outdated patterns
- **Discoverable:** Clear naming, good README, cross-linking

---

## References

- [CONSTITUTION.md](../specs/CONSTITUTION.md) - Quality standards that guidance implements
- [Spec Directory](../specs/) - Specifications that guidance supports
- [Plan Directory](../plans/) - Plans that reference guidance patterns
