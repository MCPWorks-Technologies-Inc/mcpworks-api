"""Tests for per-agent access control rule evaluation."""

from mcpworks_api.core.agent_access import (
    check_function_access,
    check_state_access,
    filter_state_keys,
)


class TestCheckFunctionAccess:
    def test_no_rules_allows_all(self):
        assert check_function_access(None, "billing", "charge") == (True, None)
        assert check_function_access({}, "billing", "charge") == (True, None)
        assert check_function_access({"function_rules": []}, "billing", "charge") == (True, None)

    def test_allow_services_permits_matching(self):
        rules = {
            "function_rules": [
                {"id": "r-1", "type": "allow_services", "patterns": ["social", "content"]}
            ]
        }
        assert check_function_access(rules, "social", "post") == (True, None)
        assert check_function_access(rules, "content", "create") == (True, None)

    def test_allow_services_blocks_non_matching(self):
        rules = {
            "function_rules": [
                {"id": "r-1", "type": "allow_services", "patterns": ["social", "content"]}
            ]
        }
        allowed, rule_id = check_function_access(rules, "billing", "charge")
        assert allowed is False
        assert rule_id == "r-1"

    def test_deny_services_blocks_matching(self):
        rules = {
            "function_rules": [
                {"id": "r-2", "type": "deny_services", "patterns": ["billing", "admin"]}
            ]
        }
        allowed, rule_id = check_function_access(rules, "billing", "charge")
        assert allowed is False
        assert rule_id == "r-2"

    def test_deny_services_allows_non_matching(self):
        rules = {
            "function_rules": [{"id": "r-2", "type": "deny_services", "patterns": ["billing"]}]
        }
        assert check_function_access(rules, "social", "post") == (True, None)

    def test_deny_functions_blocks_matching(self):
        rules = {
            "function_rules": [
                {"id": "r-3", "type": "deny_functions", "patterns": ["admin.delete_*"]}
            ]
        }
        allowed, rule_id = check_function_access(rules, "admin", "delete_user")
        assert allowed is False
        assert rule_id == "r-3"

    def test_deny_functions_allows_non_matching(self):
        rules = {
            "function_rules": [
                {"id": "r-3", "type": "deny_functions", "patterns": ["admin.delete_*"]}
            ]
        }
        assert check_function_access(rules, "admin", "list_users") == (True, None)

    def test_allow_functions_permits_matching(self):
        rules = {
            "function_rules": [
                {
                    "id": "r-4",
                    "type": "allow_functions",
                    "patterns": ["social.post_*", "social.list_*"],
                }
            ]
        }
        assert check_function_access(rules, "social", "post_tweet") == (True, None)
        assert check_function_access(rules, "social", "list_posts") == (True, None)

    def test_allow_functions_blocks_non_matching(self):
        rules = {
            "function_rules": [
                {"id": "r-4", "type": "allow_functions", "patterns": ["social.post_*"]}
            ]
        }
        allowed, rule_id = check_function_access(rules, "social", "delete_post")
        assert allowed is False
        assert rule_id == "r-4"

    def test_deny_takes_precedence_over_allow_services(self):
        rules = {
            "function_rules": [
                {"id": "r-allow", "type": "allow_services", "patterns": ["admin"]},
                {"id": "r-deny", "type": "deny_functions", "patterns": ["admin.delete_*"]},
            ]
        }
        allowed, rule_id = check_function_access(rules, "admin", "delete_user")
        assert allowed is False
        assert rule_id == "r-deny"

        assert check_function_access(rules, "admin", "list_users") == (True, None)

    def test_deny_services_takes_precedence_over_allow_services(self):
        rules = {
            "function_rules": [
                {"id": "r-allow", "type": "allow_services", "patterns": ["*"]},
                {"id": "r-deny", "type": "deny_services", "patterns": ["billing"]},
            ]
        }
        allowed, rule_id = check_function_access(rules, "billing", "charge")
        assert allowed is False
        assert rule_id == "r-deny"

    def test_glob_patterns(self):
        rules = {"function_rules": [{"id": "r-1", "type": "allow_services", "patterns": ["soc*"]}]}
        assert check_function_access(rules, "social", "post") == (True, None)
        assert check_function_access(rules, "society", "join") == (True, None)
        allowed, _ = check_function_access(rules, "billing", "charge")
        assert allowed is False

    def test_multiple_deny_rules(self):
        rules = {
            "function_rules": [
                {"id": "r-1", "type": "deny_services", "patterns": ["billing"]},
                {"id": "r-2", "type": "deny_functions", "patterns": ["admin.delete_*"]},
            ]
        }
        allowed, rule_id = check_function_access(rules, "billing", "charge")
        assert allowed is False
        assert rule_id == "r-1"

        allowed, rule_id = check_function_access(rules, "admin", "delete_user")
        assert allowed is False
        assert rule_id == "r-2"

        assert check_function_access(rules, "admin", "list_users") == (True, None)


class TestCheckStateAccess:
    def test_no_rules_allows_all(self):
        assert check_state_access(None, "secrets.api_key") == (True, None)
        assert check_state_access({}, "secrets.api_key") == (True, None)
        assert check_state_access({"state_rules": []}, "any.key") == (True, None)

    def test_allow_keys_permits_matching(self):
        rules = {
            "state_rules": [
                {"id": "r-s1", "type": "allow_keys", "patterns": ["content.*", "cache.*"]}
            ]
        }
        assert check_state_access(rules, "content.posts") == (True, None)
        assert check_state_access(rules, "cache.recent") == (True, None)

    def test_allow_keys_blocks_non_matching(self):
        rules = {"state_rules": [{"id": "r-s1", "type": "allow_keys", "patterns": ["content.*"]}]}
        allowed, rule_id = check_state_access(rules, "secrets.api_key")
        assert allowed is False
        assert rule_id == "r-s1"

    def test_deny_keys_blocks_matching(self):
        rules = {"state_rules": [{"id": "r-s2", "type": "deny_keys", "patterns": ["secrets.*"]}]}
        allowed, rule_id = check_state_access(rules, "secrets.api_key")
        assert allowed is False
        assert rule_id == "r-s2"

    def test_deny_keys_allows_non_matching(self):
        rules = {"state_rules": [{"id": "r-s2", "type": "deny_keys", "patterns": ["secrets.*"]}]}
        assert check_state_access(rules, "content.posts") == (True, None)

    def test_deny_takes_precedence_over_allow(self):
        rules = {
            "state_rules": [
                {"id": "r-allow", "type": "allow_keys", "patterns": ["*"]},
                {"id": "r-deny", "type": "deny_keys", "patterns": ["secrets.*"]},
            ]
        }
        allowed, rule_id = check_state_access(rules, "secrets.api_key")
        assert allowed is False
        assert rule_id == "r-deny"

        assert check_state_access(rules, "content.posts") == (True, None)

    def test_glob_patterns(self):
        rules = {
            "state_rules": [
                {"id": "r-s1", "type": "allow_keys", "patterns": ["cache.*", "content.post_*"]}
            ]
        }
        assert check_state_access(rules, "cache.anything") == (True, None)
        assert check_state_access(rules, "content.post_123") == (True, None)
        allowed, _ = check_state_access(rules, "content.comment_1")
        assert allowed is False


class TestFilterStateKeys:
    def test_no_rules_returns_all(self):
        keys = ["a", "b", "c"]
        assert filter_state_keys(None, keys) == keys

    def test_filters_denied_keys(self):
        rules = {"state_rules": [{"id": "r-1", "type": "deny_keys", "patterns": ["secrets.*"]}]}
        keys = ["content.posts", "secrets.api_key", "cache.recent", "secrets.token"]
        result = filter_state_keys(rules, keys)
        assert result == ["content.posts", "cache.recent"]

    def test_filters_to_allowed_keys_only(self):
        rules = {"state_rules": [{"id": "r-1", "type": "allow_keys", "patterns": ["content.*"]}]}
        keys = ["content.posts", "secrets.api_key", "content.drafts"]
        result = filter_state_keys(rules, keys)
        assert result == ["content.posts", "content.drafts"]
