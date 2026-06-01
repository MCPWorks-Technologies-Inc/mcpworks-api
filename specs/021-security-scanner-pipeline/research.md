# Research: Pluggable Security Scanner Pipeline

## OSS Prompt Injection Defense Landscape

| Tool | Stars | License | Approach | MCPWorks Fit |
|------|-------|---------|----------|-------------|
| **LLM Guard** (Protect AI) | 2.8K | MIT | DeBERTa classifier + 36 scanners | HIGH — Python, FastAPI-native, use as Python scanner |
| **NeMo Guardrails** (NVIDIA) | 5.9K | Custom | Colang DSL + LLM-as-judge | Medium — heavyweight, overkill |
| **Guardrails AI** | 6.6K | Apache-2.0 | Validation framework | Low — output quality, not security |
| **ProtectAI DeBERTa** | — | Apache-2.0 | Binary classifier model | HIGH — 10ms inference, use via LLM Guard |
| **Promptfoo** | 19.7K | MIT | Red-teaming/testing | HIGH — for testing, not runtime |
| **Rebuff** | 1.5K | Apache-2.0 | Multi-layer + canary tokens | NONE — archived |
| **Vigil** | 469 | Apache-2.0 | YARA + classifiers | Low — abandoned |

## Decision 1: Pipeline Architecture, Not Monolithic Scanner

**Decision**: Build a configurable scanner pipeline, not a specific defense engine.

**Rationale**: No single technique catches everything. Regex catches 60-70% of naive attacks. Classifiers catch 80-90% including sophisticated attacks. LLM-as-judge catches novel attacks. Structural defenses (output parsing, trust boundaries) are most robust but can't detect all attacks. The pipeline lets users combine layers appropriate to their risk profile.

**Academic support**: Google DeepMind (Gemini defense paper), Microsoft (indirect injection defense), OWASP LLM Top 10 — all recommend multi-layer defense-in-depth.

## Decision 2: Three Scanner Types

**Decision**: builtin (zero-dep), webhook (HTTP), python (importable callable).

**Rationale**:
- **builtin**: Ships with MCPWorks. Regex + heuristic + secret scan + trust boundary. No external deps. This is the floor.
- **webhook**: Any HTTP service. User runs Lakera Guard, custom classifier, LLM-as-judge — anything that speaks HTTP. Platform-agnostic.
- **python**: In-process callable. For self-hosters who want LLM Guard or custom models without network hops. Fastest option for ML classifiers.

## Decision 3: Refactor Existing Code Into Built-in Scanners

**Decision**: Wrap existing `injection_scan.py`, `credential_scan.py`, and `trust_boundary.py` as built-in scanner implementations.

**Rationale**: This code already works and is tested. Refactoring it into the scanner interface makes it composable with new scanner types without breaking existing behavior.

## Decision 4: Per-namespace Pipeline Config in JSONB

**Decision**: Store pipeline config as JSONB on the namespace model, with global defaults when not configured.

**Rationale**: Consistent with how access_rules (spec 018) and mcp_server settings are stored. JSONB avoids a separate table and allows flexible config per scanner type.

## Decision 5: Scan Results in Execution Records

**Decision**: Store per-scanner scan results in `backend_metadata` on the Execution model (spec 020).

**Rationale**: Execution debugging (spec 020) already persists backend_metadata. Adding scan results there provides observability without a new table. Scan results are queryable through the same execution API.

## Decision 6: Fail-Open by Default

**Decision**: When all scanners error or timeout, default behavior is fail-open (allow with warning log).

**Rationale**: Fail-closed would mean a scanner outage blocks all function execution. For most self-hosters, availability is more important than blocking every possible injection. Security-sensitive deployments can set fail-closed per namespace.

## What Actually Works vs. Theater

| Technique | Effectiveness | Our Approach |
|-----------|--------------|-------------|
| Regex/heuristic | Low alone, good as fast pre-filter | Built-in scanner (Layer 1) |
| ML classifier (DeBERTa) | Medium — 70% F1 out-of-domain | Available via Python scanner (LLM Guard) |
| LLM-as-judge | Medium-high, expensive | Available via webhook or Python scanner |
| Canary tokens | Medium for detection | Future enhancement |
| Trust boundaries | High — structural defense | Built-in scanner (already implemented) |
| Output parsing | Highest effectiveness | Function output_trust + schema validation |
| Sandwich defense | Low — security theater | NOT implemented |
| Same-model-as-judge | Vulnerable to same attacks | NOT recommended |

## MCP-Specific Threat Vectors

1. **Indirect injection via function output** — most critical for MCPWorks. Function returns data containing "ignore previous instructions." Pipeline scans output before it reaches AI context.
2. **Tool poisoning** — malicious instructions in tool descriptions. Mitigated by versioned function definitions and admin review.
3. **Tool shadowing** — namespace collisions. Mitigated by namespace isolation.
4. **Rug pull attacks** — tool definitions change after approval. Relevant for MCP Server Plugins (A1), not native functions.
