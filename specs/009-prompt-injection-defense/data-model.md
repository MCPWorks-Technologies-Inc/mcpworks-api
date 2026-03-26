# Data Model: Prompt Injection Defense

**Feature**: 009-prompt-injection-defense
**Date**: 2026-03-26

## Modified Entities

### Function

| Field | Change | Type | Constraints | Description |
|-------|--------|------|-------------|-------------|
| output_trust | NEW | VARCHAR(10) | NOT NULL | `prompt` (trusted output) or `data` (untrusted external content). Required on creation. |

**Migration**: Backfill existing rows to `prompt`. Remove default after backfill so application enforces explicit value.

### NamespaceMcpServer

| Field | Change | Type | Constraints | Description |
|-------|--------|------|-------------|-------------|
| rules | NEW | JSONB | NOT NULL, DEFAULT '{"request":[],"response":[]}' | Per-server request/response rules |

**Default rules on creation**: `wrap_trust_boundary` + `scan_injection(strictness=warn)` on all tools.

## New Module: sandbox/injection_scan.py

```python
@dataclass
class InjectionMatch:
    pattern_name: str      # e.g., "instruction_override"
    matched_text: str      # the matched substring (truncated to 200 chars)
    severity: str          # "low", "medium", "high"
    position: int          # character offset in source text

_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # (pattern_name, compiled_regex, severity)
    ("instruction_override", ..., "high"),
    ("role_reassignment", ..., "high"),
    ("system_prompt_injection", ..., "high"),
    ("delimiter_injection", ..., "medium"),
    ("authority_claim", ..., "medium"),
    ("output_manipulation", ..., "medium"),
    ("base64_obfuscation", ..., "low"),
    ("indirect_instruction", ..., "low"),
]

def scan_for_injections(text: str) -> list[InjectionMatch]: ...
def scan_json_for_injections(data: Any) -> list[InjectionMatch]: ...
```

## New Module: core/trust_boundary.py

```python
def wrap_function_output(result_text: str, service: str, function: str) -> str:
    """Wrap a data-trust function result with trust boundary markers."""
    return (
        f'[UNTRUSTED_OUTPUT function="{service}.{function}" trust="data"]\n'
        f'{result_text}\n'
        f'[/UNTRUSTED_OUTPUT]'
    )

def wrap_mcp_response(
    response_text: str,
    server: str,
    tool: str,
    injections_found: int = 0,
) -> str:
    """Wrap a RemoteMCP response with trust boundary markers."""
    return (
        f'[EXTERNAL_DATA source="{server}" tool="{tool}" trust="untrusted" injections_found={injections_found}]\n'
        f'{response_text}\n'
        f'[/EXTERNAL_DATA]'
    )

def wrap_injection_warning(text: str, pattern: str, severity: str) -> str:
    """Wrap a flagged text segment with injection warning markers."""
    return (
        f'[INJECTION_WARNING pattern="{pattern}" severity="{severity}"]\n'
        f'{text}\n'
        f'[/INJECTION_WARNING]'
    )
```

## Rule Schema

### Request Rules

| Type | Fields | Behavior |
|------|--------|----------|
| `inject_param` | tool (glob), key, value or prepend/append | Add/override parameter before call |
| `block_tool` | tool (glob) | Reject call with "Tool blocked by namespace rule" |
| `require_param` | tool (glob), key | Reject if parameter missing |
| `cap_param` | tool (glob), key, max | Enforce numeric ceiling |

### Response Rules

| Type | Fields | Behavior |
|------|--------|----------|
| `wrap_trust_boundary` | tools (glob) | Wrap with EXTERNAL_DATA markers |
| `scan_injection` | tools (glob), strictness | Run scanner, apply warn/flag/block |
| `strip_html` | tools (glob) | Remove HTML tags from text |
| `inject_header` | tools (glob), text | Prepend warning text |
| `redact_fields` | tools (glob), fields (dot-paths) | Remove keys from JSON response |

### Rule Identity

Each rule has an `id` field (auto-generated UUID or user-provided string). Used for `remove_mcp_server_rule`.
