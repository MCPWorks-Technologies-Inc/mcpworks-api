# Research: Procedures Framework

**Branch**: `013-add-procedures-framework`

## R1: Orchestration Integration

**Decision**: Add a `procedure` orchestration mode to the existing `run_orchestration()` function rather than creating a separate execution engine.

**Rationale**: The orchestrator already handles the AI conversation loop, tool dispatch, token tracking, and result capture. Procedure mode constrains which tools the LLM can call at each step and enforces sequential advancement. This is a behavioral modification of the existing loop, not a new system.

**Key changes to orchestrator**:
- New `run_procedure_orchestration()` function that wraps `run_orchestration()` with step-by-step control
- Each step sets the system prompt to include: step instructions, required function name, accumulated context
- After each AI turn, check if the required function was called — if yes, capture result and advance; if no, retry
- Step results persisted to `ProcedureExecution` after each step completes

**Alternatives considered**:
- Separate execution engine: Cleaner separation but duplicates AI client setup, tool dispatch, token tracking. More code, more maintenance.
- Modifying `_dispatch_tool` to intercept: Too invasive — changes the core tool dispatch path for all orchestration modes.

## R2: Data Model Design

**Decision**: Three new tables — `procedures`, `procedure_versions`, `procedure_executions`. Steps and step results are stored as JSONB arrays within their parent records.

**Rationale**: Steps are always accessed with their parent (you never query a step independently). JSONB arrays avoid join overhead and keep the step ordering implicit in array position. This matches how function versions store `input_schema`/`output_schema` as JSONB.

**Step definition structure** (in procedure_versions.steps JSONB):
```json
[
  {
    "step_number": 1,
    "name": "authenticate",
    "function_ref": "social.bluesky-auth",
    "instructions": "Authenticate with BlueSky using stored credentials",
    "failure_policy": "required",
    "max_retries": 3,
    "validation": {"required_fields": ["access_token"]}
  }
]
```

**Step result structure** (in procedure_executions.step_results JSONB):
```json
[
  {
    "step_number": 1,
    "name": "authenticate",
    "status": "success",
    "function_called": "social.bluesky-auth",
    "result": {"access_token": "..."},
    "attempts": [
      {"started_at": "...", "completed_at": "...", "success": true}
    ]
  }
]
```

**Alternatives considered**:
- Separate `procedure_steps` table: Normalized but adds joins for every read. Steps are small and always needed together.
- Embedding versions in the procedures table: Loses immutability — can't keep old versions for audit.

## R3: Validation Rules

**Decision**: Simple declarative validation with `required_fields` check. A step's validation rule specifies field names that must exist in the function result.

**Rationale**: The spec says "simple declarative format." Checking for required fields covers the most common case (did the function return the data we need?) without introducing arbitrary code execution in the validation path.

**Format**: `{"required_fields": ["field1", "field2"]}` — each field must be a key in the top-level result dict.

**Alternatives considered**:
- JSON Schema validation: More powerful but overkill for step validation. The function's own output_schema already handles structural validation.
- Regex matching on result string: Fragile and hard to maintain.
- No validation: Simpler but loses the ability to catch "function returned successfully but with wrong data."

## R4: Trigger Integration

**Decision**: Add `"procedure"` to `ORCHESTRATION_MODES` tuple. Schedules and webhooks with `orchestration_mode: "procedure"` will call `run_procedure_orchestration()` instead of `run_orchestration()`.

**Rationale**: Minimal change to existing trigger infrastructure. The `orchestration_mode` field already exists on `AgentSchedule` and `AgentWebhook`. Adding a new value is backward compatible.

**New field on schedule/webhook**: `procedure_name` (optional, required when mode is "procedure").

## R5: Security — Restricted Tools

**Decision**: Add `make_procedure`, `update_procedure`, `delete_procedure` to `RESTRICTED_AGENT_TOOLS` in `ai_tools.py`.

**Rationale**: Consistent with 014-agent-security-hardening. Procedures are executable logic — agents should not be able to create them, only execute them.
