# Data Model: Agent Governance Toolkit Integration

**Date**: 2026-04-08

## Schema Changes

### Modified Table: `agents`

| Column | Type | Default | Constraint | Purpose |
|--------|------|---------|------------|---------|
| `trust_score` | INTEGER | 500 | NOT NULL, CHECK (0 <= trust_score <= 1000) | Agent behavioral trust score |
| `trust_score_updated_at` | TIMESTAMPTZ | NULL | NULLABLE | Last trust score change timestamp |

### Migration SQL

```sql
ALTER TABLE agents
  ADD COLUMN trust_score INTEGER NOT NULL DEFAULT 500,
  ADD COLUMN trust_score_updated_at TIMESTAMPTZ;

ALTER TABLE agents
  ADD CONSTRAINT ck_agents_trust_score CHECK (trust_score >= 0 AND trust_score <= 1000);
```

## Trust Score Model

### Constants

```python
TRUST_DEFAULT = 500
TRUST_MIN = 0
TRUST_MAX = 1000
TRUST_RECOVERY_CAP = 500  # recovery cannot exceed this
TRUST_RECOVERY_DELTA = 1  # per successful execution
```

### Event-Based Deltas

| Security Event Type | Delta | Rationale |
|--------------------|-------|-----------|
| `scanner.prompt_injection` | -50 | Direct attack attempt |
| `scanner.secret_leak` | -100 | High-severity data exfiltration |
| `scanner.output_blocked` | -25 | Generic output violation |
| `agent.unauthorized_access` | -50 | Access control violation |
| Default (any other security event) | -25 | Conservative degradation |

### Atomic Update Pattern

```sql
-- Degradation (on security event)
UPDATE agents
SET trust_score = GREATEST(0, trust_score - :delta),
    trust_score_updated_at = NOW()
WHERE id = :agent_id;

-- Recovery (on successful execution)
UPDATE agents
SET trust_score = LEAST(:recovery_cap, trust_score + :delta),
    trust_score_updated_at = NOW()
WHERE id = :agent_id
  AND trust_score < :recovery_cap;
```

## Extended JSONB Structures

### Scanner Pipeline Config (existing `namespaces.scanner_pipeline` JSONB)

New scanner entry type `agent_os`:

```json
{
  "id": "custom-policy-1",
  "type": "agent_os",
  "name": "agent_os",
  "direction": "both",
  "order": 0,
  "enabled": true,
  "config": {
    "policy_format": "yaml",
    "policy": "version: '1.0'\nname: custom\nrules:\n  - name: block-sql\n    condition: \"action == 'database_query'\"\n    action: deny\n    pattern: 'DROP|TRUNCATE'"
  }
}
```

Supported `policy_format` values: `"yaml"`, `"cedar"`, `"rego"`

For `cedar` and `rego`, `config.policy` contains the raw policy text.

### Agent Access Rules (existing `agents.access_rules` JSONB)

New optional field on function rules:

```json
{
  "function_rules": [
    {
      "id": "r-abc123",
      "type": "allow_functions",
      "patterns": ["sensitive-service.*"],
      "min_trust_score": 400
    }
  ]
}
```

`min_trust_score` defaults to 0 (no trust gate) when absent.

## Compliance Report Model (response-only, not persisted)

```json
{
  "namespace": "my-namespace",
  "framework": "owasp-agentic-top-10",
  "grade": "B",
  "coverage_pct": 80,
  "evaluated_at": "2026-04-08T12:00:00Z",
  "risks": [
    {
      "id": "OWASP-AT-01",
      "name": "Agent Goal Hijack",
      "status": "covered",
      "control": "scanner_pipeline with pattern_scanner (input direction)",
      "remediation": null
    },
    {
      "id": "OWASP-AT-10",
      "name": "Rogue Agents",
      "status": "gap",
      "control": null,
      "remediation": "Enable trust scoring on agents and set min_trust_score on sensitive functions"
    }
  ]
}
```

Status values: `"covered"`, `"partial"`, `"gap"`
Grade calculation: A (90-100%), B (80-89%), C (70-79%), D (60-69%), F (<60%)
