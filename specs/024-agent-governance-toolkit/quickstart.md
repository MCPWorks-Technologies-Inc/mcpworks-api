# Quickstart: Agent Governance Toolkit Integration

## Prerequisites

- MCPWorks API running (local or production)
- A namespace with at least one agent

## 1. Install Optional Dependencies

```bash
# Agent OS policy engine (Cedar + Rego support)
pip install agent-os-kernel[full]

# Agent Compliance (OWASP attestation)
pip install agent-compliance
```

These are optional — MCPWorks runs without them. Scanner entries referencing `agent_os` will log a warning and skip if the package is missing.

## 2. Add Agent OS Scanner to Namespace

Via MCP `add_security_scanner` tool:

```json
{
  "type": "agent_os",
  "name": "agent_os",
  "direction": "both",
  "order": 0,
  "config": {
    "policy_format": "yaml",
    "policy": "version: '1.0'\nname: read-only\nrules:\n  - name: block-writes\n    condition: \"action == 'database_query'\"\n    action: deny\n    pattern: 'INSERT|UPDATE|DELETE|DROP'"
  }
}
```

Cedar policy example:
```json
{
  "config": {
    "policy_format": "cedar",
    "policy": "permit(principal, action == Action::\"read\", resource);\nforbid(principal, action == Action::\"delete\", resource);"
  }
}
```

## 3. Set Trust Score Gates on Functions

Via `configure_agent_access`:

```json
{
  "agent_name": "my-agent",
  "rule": {
    "type": "allow_functions",
    "patterns": ["sensitive-service.*"],
    "min_trust_score": 400
  }
}
```

Agents with trust score below 400 will be blocked from `sensitive-service.*` functions.

## 4. Check Compliance

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.mcpworks.io/v1/namespaces/my-namespace/compliance

# With full remediation guidance:
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.mcpworks.io/v1/namespaces/my-namespace/compliance?detail=full"
```

## 5. Monitor Trust Scores

Trust scores degrade automatically on security events:
- Prompt injection detected: -50 points
- Secret leak attempt: -100 points
- Other violations: -25 points

Scores recover slowly (+1 per successful execution, capped at 500).

Admin can manually set trust score:
```json
{
  "agent_name": "my-agent",
  "trust_score": 500
}
```

## Architecture

```
Function Execution Request
    │
    ├── check_function_access() ← trust_score gate (NEW)
    │
    ├── scanner_pipeline.evaluate_pipeline()
    │   ├── agent_os scanner (NEW, order 0)  ← Cedar/Rego/YAML policy
    │   ├── pattern_scanner (existing, order 1)
    │   ├── secret_scanner (existing, order 2)
    │   └── trust_boundary (existing, order 3)
    │
    ├── execute function
    │
    └── on security event → degrade trust_score (NEW)
```
