# Implementation Plan: Schema-Driven Procedure Input Mappings

**Branch**: `019-schema-driven-procedures` | **Date**: 2026-04-16 | **Spec**: [spec.md](spec.md)

## Summary

Add `input_mapping` and `output_mapping` to procedure steps. Input mappings are JSONPath expressions resolved deterministically before presenting the step to the inner AI. Output mappings extract specific fields from step results into accumulated context. Backward compatible — steps without mappings behave as before.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: No new deps — lightweight JSONPath resolver (stdlib only)
**Storage**: No migration — steps are JSONB on procedure_versions, new fields are additional dict keys
**Integration Points**:
- `orchestrator.py:1255` — resolve input_mapping before AI prompt
- `orchestrator.py:1399` — apply output_mapping before context accumulation
- `procedure_service.py:73` — validate mappings at authoring time

## Project Structure

```text
src/mcpworks_api/
├── services/
│   ├── procedure_service.py    # MODIFIED — validate input/output_mapping at authoring
│   └── jsonpath.py             # NEW — lightweight JSONPath resolver
├── tasks/
│   └── orchestrator.py         # MODIFIED — resolve mappings in step loop

tests/unit/
├── test_jsonpath.py            # NEW — resolver tests
└── test_procedure_mappings.py  # NEW — mapping validation tests
```
