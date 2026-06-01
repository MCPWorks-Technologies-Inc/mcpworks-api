# Testing Requirements

## Coverage Targets

- **Minimum:** 80% overall, 95% for usage tracking
- Unit tests for all business logic
- Integration tests for provider interfaces
- End-to-end tests for critical workflows

## Commands

```bash
pytest tests/unit/ -q                    # Unit tests (fast, no DB)
pytest tests/integration/ -v             # Integration tests (needs Postgres)
pytest tests/ -v --cov=src               # With coverage
pytest tests/unit/test_specific.py -v    # Single file
```

## Test Organization

- `tests/unit/` — Pure logic, no DB, no network. Run locally.
- `tests/integration/` — Needs running Postgres. Run in CI.
- MCP tests auto-skip via `pytest.importorskip("mcp")` when mcp package not installed.

## Mock Data

Use fixtures for:
- Provider API responses (Stripe, etc.)
- Database state
- Usage records and subscription tiers
- Workflow execution scenarios

Location: `tests/fixtures/`
