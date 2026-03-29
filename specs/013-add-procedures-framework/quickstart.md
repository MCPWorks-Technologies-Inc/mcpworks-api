# Quickstart: Procedures Framework

**Branch**: `013-add-procedures-framework`

## Implementation Order

1. Data model (`models/procedure.py`) + migration
2. Schemas (`schemas/procedure.py`)
3. Procedure service CRUD (`services/procedure_service.py`)
4. MCP tool definitions (`mcp/tool_registry.py`)
5. MCP tool handlers (`mcp/create_handler.py`)
6. REST endpoints (`api/v1/procedures.py`)
7. Add procedure tools to RESTRICTED_AGENT_TOOLS (`core/ai_tools.py`)
8. Procedure execution engine in orchestrator (`tasks/orchestrator.py`)
9. Trigger integration — schedule/webhook support (`tasks/scheduler.py`, `api/v1/webhooks.py`)
10. Tests
11. Documentation

## Critical Path

```
[1] Data model → [2] Schemas → [3] Service → [4-6] Tools + API (parallel)
                                            → [7] Security restriction
                                            → [8] Execution engine → [9] Triggers
                                                                    → [10] Tests
                                                                    → [11] Docs
```

## Smoke Test

1. Create a service with 2 functions: `test.step-one` (returns `{"token": "abc"}`) and `test.step-two` (returns `{"posted": true}`)
2. Create a procedure:
   ```
   make_procedure(service="test", name="two-step", steps=[
     {"name": "auth", "function_ref": "test.step-one", "instructions": "Call step-one to get a token", "failure_policy": "required"},
     {"name": "post", "function_ref": "test.step-two", "instructions": "Call step-two using the token from step 1", "failure_policy": "required"}
   ])
   ```
3. Describe it: `describe_procedure(service="test", name="two-step")` — verify 2 steps shown
4. Execute it via chat: `chat_with_agent(name="...", message="Run the two-step procedure")`
5. Or directly: `run_procedure(service="test", name="two-step")`
6. Check execution: `list_procedure_executions(service="test", name="two-step")` — verify completed with 2 step results
7. Inspect audit: `describe_procedure_execution(execution_id="...")` — verify each step has function output captured
8. Test failure: Create a procedure with a step referencing a non-existent function — verify immediate failure
9. Test retry: Create a procedure with `max_retries: 2` and a function that fails — verify 2 retry attempts in the execution record
