"""Unit tests for procedure step input/output mapping validation."""

from mcpworks_api.services.jsonpath import validate_expression


class TestMappingValidation:
    def test_valid_simple_path(self):
        assert validate_expression("$.text") is None

    def test_valid_array_path(self):
        assert validate_expression("$.posts[0]") is None

    def test_valid_step_chaining(self):
        assert validate_expression("$.steps.post-root.result.uri") is None

    def test_valid_nested_array(self):
        assert validate_expression("$.data[2].name") is None

    def test_invalid_no_dollar(self):
        assert validate_expression("posts[0]") is not None

    def test_invalid_empty(self):
        assert validate_expression("$.") is not None

    def test_step_ordering_logic(self):
        step_names_so_far = ["post-root"]
        expr = "$.steps.post-root.result.uri"
        ref_step = expr.split(".")[2]
        assert ref_step in step_names_so_far

    def test_step_ordering_fails_for_future_step(self):
        step_names_so_far = ["post-root"]
        expr = "$.steps.post-reply.result.uri"
        ref_step = expr.split(".")[2]
        assert ref_step not in step_names_so_far
