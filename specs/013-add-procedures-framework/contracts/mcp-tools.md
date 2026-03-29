# MCP Tool Contracts: Procedures Framework

**Branch**: `013-add-procedures-framework`

## New Tool: `make_procedure`

```json
{
  "name": "make_procedure",
  "description": "Create a procedure — an ordered sequence of steps that each call a specific function. The orchestrator enforces step-by-step execution and captures actual function results as proof.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service": {"type": "string", "description": "Service name"},
      "name": {"type": "string", "description": "Procedure name"},
      "description": {"type": "string", "description": "What this procedure does"},
      "steps": {
        "type": "array",
        "minItems": 1,
        "maxItems": 20,
        "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string", "description": "Step name"},
            "function_ref": {"type": "string", "description": "Function to call (service.function format)"},
            "instructions": {"type": "string", "description": "Instructions for the AI at this step"},
            "failure_policy": {"type": "string", "enum": ["required", "allowed", "skip"], "default": "required"},
            "max_retries": {"type": "integer", "minimum": 0, "maximum": 5, "default": 1},
            "validation": {"type": "object", "description": "Optional: {required_fields: ['field1']}"}
          },
          "required": ["name", "function_ref", "instructions"]
        }
      }
    },
    "required": ["service", "name", "steps"]
  }
}
```

## New Tool: `update_procedure`

```json
{
  "name": "update_procedure",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service": {"type": "string"},
      "name": {"type": "string"},
      "description": {"type": "string"},
      "steps": {"type": "array", "description": "New step definitions (creates new version)"}
    },
    "required": ["service", "name"]
  }
}
```

## New Tool: `delete_procedure`

```json
{
  "name": "delete_procedure",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service": {"type": "string"},
      "name": {"type": "string"}
    },
    "required": ["service", "name"]
  }
}
```

## New Tool: `list_procedures`

```json
{
  "name": "list_procedures",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service": {"type": "string", "description": "Service name"}
    },
    "required": ["service"]
  }
}
```

## New Tool: `describe_procedure`

```json
{
  "name": "describe_procedure",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service": {"type": "string"},
      "name": {"type": "string"}
    },
    "required": ["service", "name"]
  }
}
```

Response includes full step definitions, version history, and recent execution summary.

## New Tool: `run_procedure`

```json
{
  "name": "run_procedure",
  "description": "Execute a procedure. The orchestrator will step through each defined step, calling the required function and capturing its result before advancing.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service": {"type": "string"},
      "name": {"type": "string"},
      "input_context": {"type": "object", "description": "Optional initial context available to step 1"}
    },
    "required": ["service", "name"]
  }
}
```

## New Tool: `list_procedure_executions`

```json
{
  "name": "list_procedure_executions",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service": {"type": "string"},
      "name": {"type": "string"},
      "status": {"type": "string", "enum": ["running", "completed", "failed"]},
      "limit": {"type": "integer", "default": 10}
    },
    "required": ["service", "name"]
  }
}
```

## New Tool: `describe_procedure_execution`

```json
{
  "name": "describe_procedure_execution",
  "inputSchema": {
    "type": "object",
    "properties": {
      "execution_id": {"type": "string", "description": "Execution UUID"}
    },
    "required": ["execution_id"]
  }
}
```

Returns full step-by-step audit trail including per-attempt details.

## Modified: `add_schedule` / `add_webhook`

Existing `orchestration_mode` enum extended with `"procedure"`. New optional `procedure_name` parameter (required when mode is procedure).

## Security: Restricted Agent Tools

`make_procedure`, `update_procedure`, `delete_procedure` added to `RESTRICTED_AGENT_TOOLS`.

`run_procedure`, `list_procedures`, `describe_procedure`, `list_procedure_executions`, `describe_procedure_execution` are available to agents during orchestration.
