"""Unit tests for lightweight JSONPath resolver."""

import pytest

from mcpworks_api.services.jsonpath import (
    JSONPathError,
    apply_output_mapping,
    resolve,
    resolve_input_mapping,
    validate_expression,
)


class TestResolve:
    def test_simple_field(self):
        assert resolve("$.name", {"name": "hello"}) == "hello"

    def test_nested_field(self):
        assert resolve("$.a.b.c", {"a": {"b": {"c": 42}}}) == 42

    def test_array_index(self):
        assert resolve("$.posts[0]", {"posts": ["first", "second"]}) == "first"

    def test_array_index_nested(self):
        ctx = {"posts": [{"text": "hello"}, {"text": "world"}]}
        assert resolve("$.posts[1].text", ctx) == "world"

    def test_step_chaining(self):
        ctx = {"steps": {"post-root": {"result": {"uri": "at://did/post/1", "cid": "abc123"}}}}
        assert resolve("$.steps.post-root.result.uri", ctx) == "at://did/post/1"

    def test_missing_key_raises(self):
        with pytest.raises(JSONPathError, match="Key 'missing' not found"):
            resolve("$.missing", {"name": "hello"})

    def test_index_out_of_range(self):
        with pytest.raises(JSONPathError, match="out of range"):
            resolve("$.posts[5]", {"posts": ["a", "b"]})

    def test_index_on_non_list(self):
        with pytest.raises(JSONPathError, match="Cannot index"):
            resolve("$.name[0]", {"name": "hello"})

    def test_field_on_non_dict(self):
        with pytest.raises(JSONPathError, match="Cannot access"):
            resolve("$.name.sub", {"name": "hello"})

    def test_missing_dollar_prefix(self):
        with pytest.raises(JSONPathError, match="must start with"):
            resolve("name", {"name": "hello"})

    def test_empty_path(self):
        with pytest.raises(JSONPathError, match="Empty path"):
            resolve("$.", {"name": "hello"})


class TestValidateExpression:
    def test_valid_simple(self):
        assert validate_expression("$.name") is None

    def test_valid_nested(self):
        assert validate_expression("$.a.b.c") is None

    def test_valid_array(self):
        assert validate_expression("$.posts[0]") is None

    def test_valid_mixed(self):
        assert validate_expression("$.steps.post-root.result.uri") is None

    def test_invalid_no_prefix(self):
        assert validate_expression("name") is not None

    def test_invalid_empty(self):
        assert validate_expression("$.") is not None

    def test_not_string(self):
        assert validate_expression(123) is not None


class TestResolveInputMapping:
    def test_full_mapping(self):
        mapping = {"text": "$.posts[0]", "parent_uri": "$.steps.post-root.result.uri"}
        ctx = {
            "posts": ["Hello world"],
            "steps": {"post-root": {"result": {"uri": "at://x"}}},
        }
        resolved, errors = resolve_input_mapping(mapping, ctx)
        assert errors == []
        assert resolved == {"text": "Hello world", "parent_uri": "at://x"}

    def test_partial_failure(self):
        mapping = {"text": "$.posts[0]", "missing": "$.nonexistent"}
        ctx = {"posts": ["Hello"]}
        resolved, errors = resolve_input_mapping(mapping, ctx)
        assert resolved == {"text": "Hello"}
        assert len(errors) == 1
        assert "missing" in errors[0]


class TestApplyOutputMapping:
    def test_extract_fields(self):
        mapping = {"post_uri": "$.uri", "post_cid": "$.cid"}
        result = {"success": True, "uri": "at://x", "cid": "abc"}
        extracted, errors = apply_output_mapping(mapping, result)
        assert errors == []
        assert extracted == {"post_uri": "at://x", "post_cid": "abc"}

    def test_non_dict_result(self):
        mapping = {"value": "$.x"}
        extracted, errors = apply_output_mapping(mapping, "not a dict")
        assert len(errors) == 1
        assert extracted == {}

    def test_missing_field(self):
        mapping = {"value": "$.missing"}
        extracted, errors = apply_output_mapping(mapping, {"other": 1})
        assert len(errors) == 1
