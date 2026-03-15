"""Input size validation — OWASP LLM10 Unbounded Consumption defense.

Validates that MCP tool inputs don't exceed safe size limits.
"""

INPUT_LIMITS: dict[str, int] = {
    "code": 100 * 1024,
    "execute_input": 1 * 1024 * 1024,
    "agent_state_value": 10 * 1024 * 1024,
    "agent_ai_config": 50 * 1024,
    "webhook_payload": 1 * 1024 * 1024,
    "description": 10 * 1024,
    "input_schema": 50 * 1024,
    "output_schema": 50 * 1024,
}


class InputTooLarge(Exception):
    def __init__(self, field: str, size: int, limit: int):
        self.field = field
        self.size = size
        self.limit = limit
        super().__init__(f"Input '{field}' is {size} bytes, max is {limit} bytes")


def validate_input_size(field: str, value: str | bytes | None) -> None:
    if value is None:
        return
    limit = INPUT_LIMITS.get(field)
    if limit is None:
        return
    size = len(value.encode("utf-8")) if isinstance(value, str) else len(value)
    if size > limit:
        raise InputTooLarge(field=field, size=size, limit=limit)
