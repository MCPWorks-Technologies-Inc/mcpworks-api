"""Lightweight JSONPath resolver for procedure step mappings.

Supports a subset of JSONPath sufficient for procedure data flow:
  $.field           — object field access
  $.field.nested    — nested field access
  $.array[0]        — array index access
  $.steps.name.result.field — step chaining
"""

import re

_SEGMENT_PATTERN = re.compile(r"([a-zA-Z_][a-zA-Z0-9_-]*)|\[(\d+)\]")


class JSONPathError(Exception):
    pass


def resolve(expression: str, context: dict) -> object:
    if not expression.startswith("$."):
        raise JSONPathError(f"Expression must start with '$.' — got: {expression}")

    path = expression[2:]
    if not path:
        raise JSONPathError("Empty path after '$.'")

    current: object = context
    segments = _SEGMENT_PATTERN.findall(path)

    raw_remaining = path
    for field, index in segments:
        if field:
            matched = field
            raw_remaining = raw_remaining[len(matched) :]
            if raw_remaining.startswith("."):
                raw_remaining = raw_remaining[1:]
            if not isinstance(current, dict):
                raise JSONPathError(
                    f"Cannot access '{field}' on {type(current).__name__} (at '{expression}')"
                )
            if field not in current:
                raise JSONPathError(f"Key '{field}' not found (at '{expression}')")
            current = current[field]
        elif index:
            matched = f"[{index}]"
            raw_remaining = raw_remaining[len(matched) :]
            if raw_remaining.startswith("."):
                raw_remaining = raw_remaining[1:]
            idx = int(index)
            if not isinstance(current, list):
                raise JSONPathError(
                    f"Cannot index [{idx}] on {type(current).__name__} (at '{expression}')"
                )
            if idx >= len(current):
                raise JSONPathError(
                    f"Index [{idx}] out of range (length {len(current)}) (at '{expression}')"
                )
            current = current[idx]

    return current


def validate_expression(expression: str) -> str | None:
    if not isinstance(expression, str):
        return "Expression must be a string"
    if not expression.startswith("$."):
        return "Expression must start with '$.'"
    path = expression[2:]
    if not path:
        return "Empty path after '$.'"
    cleaned = _SEGMENT_PATTERN.sub("", path)
    cleaned = cleaned.replace(".", "")
    if cleaned:
        return f"Invalid characters in path: '{cleaned}'"
    return None


def resolve_input_mapping(
    mapping: dict[str, str],
    context: dict,
) -> tuple[dict, list[str]]:
    resolved = {}
    errors = []
    for param_name, expression in mapping.items():
        try:
            resolved[param_name] = resolve(expression, context)
        except JSONPathError as e:
            errors.append(f"{param_name}: {e}")
    return resolved, errors


def apply_output_mapping(
    mapping: dict[str, str],
    result: object,
) -> tuple[dict, list[str]]:
    if not isinstance(result, dict):
        return {}, [f"Cannot apply output_mapping to {type(result).__name__} result"]
    extracted = {}
    errors = []
    for var_name, expression in mapping.items():
        try:
            extracted[var_name] = resolve(expression, result)
        except JSONPathError as e:
            errors.append(f"{var_name}: {e}")
    return extracted, errors
