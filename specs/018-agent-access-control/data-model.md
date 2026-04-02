# Data Model: Per-Agent Access Control

## Modified Entity: Agent

**Table**: `agents`

**New column**:

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `access_rules` | JSONB | Yes | NULL | Per-agent function and state access rules |

When `access_rules` is NULL or empty, the agent has unrestricted access (backwards compatible).

### access_rules Schema

```json
{
  "function_rules": [
    {
      "id": "r-<random8>",
      "type": "allow_services|deny_services|allow_functions|deny_functions",
      "patterns": ["pattern1", "pattern2"]
    }
  ],
  "state_rules": [
    {
      "id": "r-<random8>",
      "type": "allow_keys|deny_keys",
      "patterns": ["pattern1.*", "pattern2"]
    }
  ]
}
```

### Rule Types

**Function rules** (`function_rules`):

| Type | Description | Pattern format |
|------|-------------|----------------|
| `allow_services` | Allow functions in matching services only | Service name globs: `social`, `content*` |
| `deny_services` | Block functions in matching services | Service name globs: `billing`, `admin` |
| `allow_functions` | Allow specific functions only | `service.function` globs: `social.post_*` |
| `deny_functions` | Block specific functions | `service.function` globs: `admin.delete_*` |

**State rules** (`state_rules`):

| Type | Description | Pattern format |
|------|-------------|----------------|
| `allow_keys` | Allow matching state keys only | Key globs: `content.*`, `cache.*` |
| `deny_keys` | Block matching state keys | Key globs: `secrets.*`, `billing.*` |

### Rule ID Format

`r-` prefix + 8 random hex characters (e.g., `r-a1b2c3d4`). Consistent with existing `mcp_server_rules` ID format.

## Evaluation Logic

### Function Access Check

```
check_function_access(rules, service_name, function_name):
  qualified_name = f"{service_name}.{function_name}"
  
  1. If no function_rules → ALLOW
  2. Check deny_services: if service_name matches any pattern → DENY
  3. Check deny_functions: if qualified_name matches any pattern → DENY
  4. If any allow_services rules exist:
     - If service_name matches any allow pattern → continue to step 5
     - Else → DENY
  5. If any allow_functions rules exist:
     - If qualified_name matches any allow pattern → ALLOW
     - Else → DENY
  6. ALLOW
```

### State Access Check

```
check_state_access(rules, key):
  1. If no state_rules → ALLOW
  2. Check deny_keys: if key matches any pattern → DENY
  3. If any allow_keys rules exist:
     - If key matches any allow pattern → ALLOW
     - Else → DENY
  4. ALLOW
```

## Migration

**Alembic migration**: Add `access_rules` JSONB column to `agents` table with NULL default. No data migration needed — NULL means unrestricted.
