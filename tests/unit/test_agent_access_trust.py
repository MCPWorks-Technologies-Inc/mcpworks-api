"""Unit tests for trust score gate in check_function_access."""

from mcpworks_api.core.agent_access import check_function_access


class TestTrustScoreGate:
    def test_no_min_trust_allows_any_score(self):
        rules = {
            "function_rules": [{"id": "r-1", "type": "allow_functions", "patterns": ["svc.*"]}]
        }
        allowed, _ = check_function_access(rules, "svc", "fn", trust_score=0)
        assert allowed

    def test_score_above_threshold_allowed(self):
        rules = {
            "function_rules": [
                {
                    "id": "r-1",
                    "type": "allow_functions",
                    "patterns": ["svc.*"],
                    "min_trust_score": 400,
                }
            ]
        }
        allowed, _ = check_function_access(rules, "svc", "fn", trust_score=500)
        assert allowed

    def test_score_below_threshold_blocked(self):
        rules = {
            "function_rules": [
                {
                    "id": "r-1",
                    "type": "allow_functions",
                    "patterns": ["svc.*"],
                    "min_trust_score": 400,
                }
            ]
        }
        allowed, rule_id = check_function_access(rules, "svc", "fn", trust_score=300)
        assert not allowed
        assert rule_id == "r-1"

    def test_score_equal_to_threshold_allowed(self):
        rules = {
            "function_rules": [
                {
                    "id": "r-1",
                    "type": "allow_functions",
                    "patterns": ["svc.*"],
                    "min_trust_score": 400,
                }
            ]
        }
        allowed, _ = check_function_access(rules, "svc", "fn", trust_score=400)
        assert allowed

    def test_no_trust_score_passed_skips_gate(self):
        rules = {
            "function_rules": [
                {
                    "id": "r-1",
                    "type": "allow_functions",
                    "patterns": ["svc.*"],
                    "min_trust_score": 400,
                }
            ]
        }
        allowed, _ = check_function_access(rules, "svc", "fn")
        assert allowed

    def test_deny_rules_still_take_precedence(self):
        rules = {
            "function_rules": [
                {"id": "r-deny", "type": "deny_functions", "patterns": ["svc.fn"]},
                {
                    "id": "r-allow",
                    "type": "allow_functions",
                    "patterns": ["svc.*"],
                    "min_trust_score": 100,
                },
            ]
        }
        allowed, rule_id = check_function_access(rules, "svc", "fn", trust_score=500)
        assert not allowed
        assert rule_id == "r-deny"

    def test_multiple_rules_lowest_trust_applies(self):
        rules = {
            "function_rules": [
                {
                    "id": "r-1",
                    "type": "allow_functions",
                    "patterns": ["svc.fn"],
                    "min_trust_score": 200,
                },
                {
                    "id": "r-2",
                    "type": "allow_functions",
                    "patterns": ["svc.*"],
                    "min_trust_score": 600,
                },
            ]
        }
        allowed, _ = check_function_access(rules, "svc", "fn", trust_score=300)
        assert allowed
