"""Tests for runtime procedure enforcement — agents cannot bypass procedures."""

import json

from mcpworks_api.core.ai_tools import _build_covered_function_set


class TestBuildCoveredFunctionSet:
    def test_empty_summaries(self):
        assert _build_covered_function_set([]) == {}

    def test_single_procedure_single_function(self):
        summaries = [
            {
                "service": "social",
                "name": "post-bluesky-single",
                "description": "Post to Bluesky",
                "step_count": 2,
                "covered_functions": ["social.post-to-bluesky"],
            }
        ]
        result = _build_covered_function_set(summaries)
        assert result == {"social__post-to-bluesky": "social / post-bluesky-single"}

    def test_multiple_procedures_multiple_functions(self):
        summaries = [
            {
                "service": "social",
                "name": "post-bluesky-single",
                "step_count": 2,
                "covered_functions": [
                    "social.post-to-bluesky",
                    "social.send-discord-report",
                ],
            },
            {
                "service": "social",
                "name": "daily-intel",
                "step_count": 5,
                "covered_functions": ["social.scan-mcp-ecosystem"],
            },
        ]
        result = _build_covered_function_set(summaries)
        assert "social__post-to-bluesky" in result
        assert "social__send-discord-report" in result
        assert "social__scan-mcp-ecosystem" in result

    def test_uncovered_function_not_in_set(self):
        summaries = [
            {
                "service": "social",
                "name": "post-bluesky-single",
                "step_count": 2,
                "covered_functions": ["social.post-to-bluesky"],
            }
        ]
        result = _build_covered_function_set(summaries)
        assert "social__find-shareable-news" not in result


class TestProcedureEnforcementErrorMessage:
    def test_error_message_contains_procedure_name(self):
        covered = {"social__post-to-bluesky": "social / post-bluesky-single"}
        tool_name = "social__post-to-bluesky"
        if tool_name in covered:
            proc_label = covered[tool_name]
            svc, proc_name = proc_label.split(" / ", 1)
            error = json.dumps(
                {
                    "error": f"Direct call to '{tool_name}' is blocked — "
                    f"this function is covered by procedure '{proc_label}'. "
                    f"You MUST use run_procedure(service='{svc}', "
                    f"name='{proc_name}') instead.",
                }
            )
            parsed = json.loads(error)
            assert "blocked" in parsed["error"]
            assert "post-bluesky-single" in parsed["error"]
            assert "run_procedure" in parsed["error"]
            assert "service='social'" in parsed["error"]

    def test_uncovered_function_not_blocked(self):
        covered = {"social__post-to-bluesky": "social / post-bluesky-single"}
        assert "social__find-shareable-news" not in covered
