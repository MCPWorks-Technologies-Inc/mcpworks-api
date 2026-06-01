# Data Model: Security Scanner Pipeline

## Modified Entity: Namespace

**Table**: `namespaces`

**New column**:

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `scanner_pipeline` | JSONB | Yes | NULL | Per-namespace scanner pipeline configuration |

When `scanner_pipeline` is NULL, the global default pipeline (built-in scanners only) is used.

### scanner_pipeline Schema

```json
{
  "fallback_policy": "fail_open",
  "scanners": [
    {
      "id": "s-abc123",
      "type": "builtin",
      "name": "pattern_scanner",
      "direction": "output",
      "order": 1,
      "enabled": true,
      "config": {}
    },
    {
      "id": "s-def456",
      "type": "builtin",
      "name": "secret_scanner",
      "direction": "output",
      "order": 2,
      "enabled": true,
      "config": {}
    },
    {
      "id": "s-ghi789",
      "type": "webhook",
      "name": "lakera-guard",
      "direction": "output",
      "order": 3,
      "enabled": true,
      "config": {
        "url": "https://guard.internal/scan",
        "timeout_ms": 5000,
        "headers": {"Authorization": "Bearer xxx"}
      }
    },
    {
      "id": "s-jkl012",
      "type": "python",
      "name": "llm-guard-injection",
      "direction": "both",
      "order": 4,
      "enabled": true,
      "config": {
        "module": "mcpworks_scanners.llm_guard_adapter",
        "function": "scan",
        "init_kwargs": {"threshold": 0.8}
      }
    }
  ]
}
```

### Scanner Types

| Type | Config Fields | Description |
|------|--------------|-------------|
| `builtin` | `name` (pattern_scanner, secret_scanner, trust_boundary) | Ships with MCPWorks, zero dependencies |
| `webhook` | `url`, `timeout_ms`, `headers` (optional) | HTTP POST to external service |
| `python` | `module`, `function` (default: "scan"), `init_kwargs` (optional) | Importable Python callable |

### Scanner ID Format

`s-` prefix + 8 random hex characters (e.g., `s-a1b2c3d4`).

## New Dataclass: ScanVerdict

Not persisted — runtime only. Stored serialized in `executions.backend_metadata.scan_results`.

```python
@dataclass
class ScanVerdict:
    action: str          # "pass" | "flag" | "block"
    score: float         # 0.0 - 1.0 confidence
    reason: str          # human-readable explanation
    scanner_name: str    # which scanner produced this
    timing_ms: float     # how long the scanner took
```

## New Dataclass: PipelineResult

Not persisted — runtime only. Serialized into execution records.

```python
@dataclass
class PipelineResult:
    final_action: str              # highest severity across all verdicts
    final_score: float             # score from the deciding scanner
    verdicts: list[ScanVerdict]    # per-scanner results
    total_ms: float                # total pipeline evaluation time
    content_hash: str              # SHA-256 of scanned content (for audit, not content itself)
```

## Global Default Pipeline

When no `scanner_pipeline` is configured on a namespace:

```python
DEFAULT_PIPELINE = {
    "fallback_policy": "fail_open",
    "scanners": [
        {"id": "default-pattern", "type": "builtin", "name": "pattern_scanner", "direction": "output", "order": 1, "enabled": True, "config": {}},
        {"id": "default-secret", "type": "builtin", "name": "secret_scanner", "direction": "output", "order": 2, "enabled": True, "config": {}},
        {"id": "default-trust", "type": "builtin", "name": "trust_boundary", "direction": "output", "order": 3, "enabled": True, "config": {}},
    ],
}
```

## Migration

Add `scanner_pipeline` JSONB column to `namespaces` table with NULL default. No data migration needed.
