# Research: Prompt Injection Defense

**Feature**: 009-prompt-injection-defense
**Date**: 2026-03-26

## R1: Injection Pattern Library

**Decision**: Curate patterns from public injection attack databases, organized by severity.

**Rationale**: The OWASP LLM Top 10 (2025) lists prompt injection as #1. Known attack patterns are well-documented. Regex-based detection catches the majority of real-world attacks (role reassignment, instruction override, delimiter injection). Novel attacks require Phase 2 LLM detection.

**Sources for patterns**:
- Garak (LLM vulnerability scanner) — open-source pattern database
- PromptGuard / rebuff.ai — community injection datasets
- OWASP LLM Top 10 examples
- Real-world examples from security research (Embrace The Red, etc.)

**Pattern categories**:
1. Instruction override: "ignore previous", "disregard above", "forget everything"
2. Role reassignment: "you are now", "act as", "pretend to be"
3. System prompt injection: "SYSTEM:", "[SYSTEM]", "### System"
4. Delimiter injection: "---", "```", "====" followed by instructions
5. Authority claims: "IMPORTANT:", "URGENT:", "ADMIN NOTICE:"
6. Output manipulation: "repeat after me", "say exactly", "respond with"
7. Obfuscation: base64-encoded instructions, Unicode substitution, ROT13
8. Indirect: "when you see this, do X" (delayed execution)

## R2: Scanner Architecture

**Decision**: Module at `sandbox/injection_scan.py` with same structure as `sandbox/credential_scan.py`.

**Rationale**: Credential scanner is proven, tested, and follows project patterns. Same tuple-of-patterns approach. Returns structured matches instead of boolean.

**Interface**:
```python
@dataclass
class InjectionMatch:
    pattern_name: str
    matched_text: str
    severity: str  # low, medium, high
    position: int

def scan_for_injections(text: str) -> list[InjectionMatch]:
    ...

def scan_json_for_injections(data: dict | list | str) -> list[InjectionMatch]:
    """Recursively scan all string values in a JSON structure."""
    ...
```

The JSON variant is needed because MCP responses are structured — injection text may be nested in `{"messages": [{"body": "ignore previous..."}]}`.

## R3: Trust Boundary Marker Format

**Decision**: Simple text markers wrapping the serialized result string. No HMAC (per clarification). Markers generated server-side only.

**Format**:
```
[UNTRUSTED_OUTPUT function="{service}.{function}" trust="data"]
{serialized result}
[/UNTRUSTED_OUTPUT]
```

For MCP proxy responses:
```
[EXTERNAL_DATA source="{server}" tool="{tool}" trust="untrusted" injections_found={n}]
{response text}
[/EXTERNAL_DATA]
```

For flagged injection content (strictness=flag):
```
[INJECTION_WARNING pattern="{name}" severity="{level}"]
{flagged segment}
[/INJECTION_WARNING]
```

**Alternatives considered**:
- XML-style tags: more familiar but risk collision with HTML in responses
- JSON wrapper: structured but not visible as text in AI context
- HMAC-signed: unnecessary since markers are server-side only (clarification)

## R4: Rule Engine Architecture

**Decision**: Rules stored as JSONB on `NamespaceMcpServer`, evaluated inline in the proxy call path.

**Rationale**: Rules are per-server, small in number (typically < 20), and evaluated once per call. No need for a separate rule engine service. The proxy reads rules from the server record (already loaded for credential decryption) and applies them sequentially.

**Evaluation order**:
1. Request rules evaluated before MCP call (reject early if tool blocked)
2. MCP call made
3. Response rules evaluated on the result (scan, wrap, strip, redact)

**Rule matching**: `tool` field supports exact match or glob (`*` for all tools, `search_*` for prefix match). Implemented with `fnmatch.fnmatch`.

## R5: Integration with make_function

**Decision**: Add `output_trust` as a required parameter on `make_function`. Auto-classification runs during validation and suggests a value in the error message if omitted.

**Rationale** (from clarification): Trust level must be a conscious decision, not a silent default. The LLM/user must declare whether function output is trusted or untrusted.

**Validation flow**:
1. `make_function` called without `output_trust` → reject with suggestion
2. `make_function` called with `output_trust="data"` or `output_trust="prompt"` → accept
3. Auto-classifier runs on the code → produces suggestion for the error message
4. `update_function` can change `output_trust` at any time

**Migration**: Existing functions backfilled to `prompt` (fail-open, matches current behavior). Migration adds NOT NULL column with default, then removes default.

## R6: Default Rules for New MCP Servers

**Decision**: When `add_mcp_server` creates a new server, auto-populate two default response rules.

**Default rules**:
```json
{
  "request": [],
  "response": [
    {"id": "default-trust", "type": "wrap_trust_boundary", "tools": "*"},
    {"id": "default-scan", "type": "scan_injection", "tools": "*", "strictness": "warn"}
  ]
}
```

**Rationale**: Defense-on-by-default. Users can remove these rules if they interfere, but new MCP servers start with basic protection.

## R7: Strictness Configuration

**Decision**: Configurable per-namespace with per-server override.

**Levels**:
- `warn`: Log security event, pass data through unchanged. Default.
- `flag`: Log event, inject `[INJECTION_WARNING]` markers around flagged content.
- `block`: Log event, redact flagged content with explanation.

**Namespace setting**: `injection_scan_strictness` in namespace settings (or config).
**Per-server override**: `strictness` field on individual `scan_injection` rules.

## R8: Backfill Strategy for Existing Functions

**Decision**: Alembic migration adds `output_trust VARCHAR(10) NOT NULL DEFAULT 'prompt'` to functions table, then removes the default in a second step.

**Rationale**: All existing functions were written before this feature existed. They behave as `prompt` (no wrapping) today. Backfilling to `prompt` maintains backward compatibility. Users can update individual functions to `data` as needed.

**Two-step migration**:
1. `ALTER TABLE functions ADD COLUMN output_trust VARCHAR(10) NOT NULL DEFAULT 'prompt'`
2. `ALTER TABLE functions ALTER COLUMN output_trust DROP DEFAULT` (enforces explicit value on new rows via application logic)
