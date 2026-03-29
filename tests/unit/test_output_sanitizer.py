"""Tests for output secret scanner — pattern detection and env var value matching."""

import pytest

from mcpworks_api.core.output_sanitizer import scrub_env_values, scrub_secrets


class TestPatternDetection:
    @pytest.mark.parametrize(
        "secret,expected_tag",
        [
            ("sk-abc123def456ghi789jkl012", "[REDACTED_API_KEY]"),
            ("sk-proj-" + "a" * 55, "[REDACTED_API_KEY]"),
            ("sk-ant-" + "b" * 55, "[REDACTED_API_KEY]"),
            ("sk_live_" + "a" * 20, "[REDACTED_STRIPE_KEY]"),
            ("sk_test_" + "b" * 20, "[REDACTED_STRIPE_KEY]"),
            ("pk_live_" + "c" * 20, "[REDACTED_STRIPE_KEY]"),
            ("pk_test_" + "d" * 20, "[REDACTED_STRIPE_KEY]"),
            ("rk_live_" + "e" * 20, "[REDACTED_STRIPE_KEY]"),
            ("rk_test_" + "f" * 20, "[REDACTED_STRIPE_KEY]"),
            ("whsec_" + "g" * 20, "[REDACTED_STRIPE_WEBHOOK]"),
            ("AKIA" + "A" * 16, "[REDACTED_AWS_KEY]"),
            ("ghp_" + "h" * 36, "[REDACTED_GITHUB_TOKEN]"),
            ("gho_" + "i" * 36, "[REDACTED_GITHUB_TOKEN]"),
            ("glpat-" + "j" * 25, "[REDACTED_GITLAB_TOKEN]"),
            ("xoxb-" + "k" * 25, "[REDACTED_SLACK_TOKEN]"),
            ("xoxp-" + "l" * 25, "[REDACTED_SLACK_TOKEN]"),
            ("xoxa-" + "m" * 25, "[REDACTED_SLACK_TOKEN]"),
        ],
    )
    def test_known_prefixes_detected(self, secret, expected_tag):
        output = f'{{"key": "{secret}"}}'
        scrubbed, count = scrub_secrets(output)
        assert count >= 1
        assert expected_tag in scrubbed
        assert secret not in scrubbed

    def test_short_string_not_flagged(self):
        output = '{"value": "sk-short"}'
        scrubbed, count = scrub_secrets(output)
        assert count == 0
        assert scrubbed == output

    def test_normal_output_unchanged(self):
        output = '{"total": 42, "provider": "openai", "status": "ok"}'
        scrubbed, count = scrub_secrets(output)
        assert count == 0
        assert scrubbed == output

    def test_nested_json_detected(self):
        secret = "sk_live_" + "x" * 30
        output = f'{{"outer": {{"inner": {{"key": "{secret}"}}}}}}'
        scrubbed, count = scrub_secrets(output)
        assert count >= 1
        assert secret not in scrubbed

    def test_multiple_secrets_in_one_output(self):
        sk = "sk_live_" + "a" * 20
        ghp = "ghp_" + "b" * 36
        output = f"keys: {sk} and {ghp}"
        scrubbed, count = scrub_secrets(output)
        assert count >= 2
        assert sk not in scrubbed
        assert ghp not in scrubbed


class TestEnvValueMatching:
    def test_exact_value_redacted(self):
        output = '{"result": "my-secret-api-key-value-12345"}'
        scrubbed, count = scrub_env_values(output, ["my-secret-api-key-value-12345"])
        assert count == 1
        assert "[REDACTED:secret_detected]" in scrubbed
        assert "my-secret-api-key-value-12345" not in scrubbed

    def test_short_value_not_redacted(self):
        output = '{"result": "abc"}'
        scrubbed, count = scrub_env_values(output, ["abc"])
        assert count == 0
        assert scrubbed == output

    def test_key_name_not_redacted(self):
        output = '{"OPENAI_API_KEY": "some-value"}'
        scrubbed, count = scrub_env_values(output, ["actual-key-value-here"])
        assert count == 0
        assert "OPENAI_API_KEY" in scrubbed

    def test_scrub_secrets_with_env_values(self):
        env_val = "my-custom-secret-token-abc123"
        output = f'{{"leaked": "{env_val}"}}'
        scrubbed, count = scrub_secrets(output, env_values=[env_val])
        assert count >= 1
        assert env_val not in scrubbed

    def test_env_value_in_nested_json(self):
        env_val = "super-secret-value-12345678"
        output = f'{{"a": {{"b": {{"c": "{env_val}"}}}}}}'
        scrubbed, count = scrub_env_values(output, [env_val])
        assert count == 1
        assert env_val not in scrubbed

    def test_exactly_8_chars_is_checked(self):
        output = '{"v": "12345678"}'
        scrubbed, count = scrub_env_values(output, ["12345678"])
        assert count == 1

    def test_7_chars_not_checked(self):
        output = '{"v": "1234567"}'
        scrubbed, count = scrub_env_values(output, ["1234567"])
        assert count == 0
