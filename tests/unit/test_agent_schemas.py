"""Unit tests for agent Pydantic schemas (schemas/agent.py).

Tests validation rules for agent names, schedule failure policies,
webhook paths, AI engine types, and channel types.
"""

import pytest
from pydantic import ValidationError

from mcpworks_api.schemas.agent import (
    CloneAgentRequest,
    ConfigureAIRequest,
    CreateAgentRequest,
    CreateChannelRequest,
    CreateScheduleRequest,
    CreateWebhookRequest,
    SetStateRequest,
)


class TestCreateAgentRequest:
    def test_valid_name(self):
        req = CreateAgentRequest(name="my-agent-1")
        assert req.name == "my-agent-1"

    def test_name_lowercased(self):
        req = CreateAgentRequest(name="MyAgent")
        assert req.name == "myagent"

    def test_single_char_name(self):
        req = CreateAgentRequest(name="a")
        assert req.name == "a"

    def test_max_length_name(self):
        name = "a" * 63
        req = CreateAgentRequest(name=name)
        assert req.name == name

    def test_name_with_hyphens(self):
        req = CreateAgentRequest(name="my-cool-agent")
        assert req.name == "my-cool-agent"

    def test_name_starting_with_hyphen_rejected(self):
        with pytest.raises(ValidationError, match="alphanumeric"):
            CreateAgentRequest(name="-bad")

    def test_name_ending_with_hyphen_rejected(self):
        with pytest.raises(ValidationError, match="alphanumeric"):
            CreateAgentRequest(name="bad-")

    def test_name_with_underscore_rejected(self):
        with pytest.raises(ValidationError, match="alphanumeric"):
            CreateAgentRequest(name="bad_name")

    def test_name_with_spaces_rejected(self):
        with pytest.raises(ValidationError, match="alphanumeric"):
            CreateAgentRequest(name="bad name")

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            CreateAgentRequest(name="")

    def test_too_long_name_rejected(self):
        with pytest.raises(ValidationError):
            CreateAgentRequest(name="a" * 64)

    def test_display_name_optional(self):
        req = CreateAgentRequest(name="agent1")
        assert req.display_name is None

    def test_display_name_set(self):
        req = CreateAgentRequest(name="agent1", display_name="My Agent")
        assert req.display_name == "My Agent"


class TestCreateScheduleRequest:
    def test_valid_continue_policy(self):
        req = CreateScheduleRequest(
            function_name="my-func",
            cron_expression="*/5 * * * *",
            failure_policy={"strategy": "continue"},
        )
        assert req.failure_policy["strategy"] == "continue"

    def test_valid_auto_disable_policy(self):
        req = CreateScheduleRequest(
            function_name="my-func",
            cron_expression="0 * * * *",
            failure_policy={"strategy": "auto_disable", "max_failures": 3},
        )
        assert req.failure_policy["max_failures"] == 3

    def test_valid_backoff_policy(self):
        req = CreateScheduleRequest(
            function_name="my-func",
            cron_expression="0 * * * *",
            failure_policy={"strategy": "backoff", "backoff_factor": 2},
        )
        assert req.failure_policy["backoff_factor"] == 2

    def test_invalid_strategy_rejected(self):
        with pytest.raises(ValidationError, match="strategy"):
            CreateScheduleRequest(
                function_name="my-func",
                cron_expression="0 * * * *",
                failure_policy={"strategy": "invalid"},
            )

    def test_auto_disable_without_max_failures_rejected(self):
        with pytest.raises(ValidationError, match="max_failures"):
            CreateScheduleRequest(
                function_name="my-func",
                cron_expression="0 * * * *",
                failure_policy={"strategy": "auto_disable"},
            )

    def test_backoff_without_factor_rejected(self):
        with pytest.raises(ValidationError, match="backoff_factor"):
            CreateScheduleRequest(
                function_name="my-func",
                cron_expression="0 * * * *",
                failure_policy={"strategy": "backoff"},
            )

    def test_missing_failure_policy_rejected(self):
        with pytest.raises(ValidationError):
            CreateScheduleRequest(
                function_name="my-func",
                cron_expression="0 * * * *",
            )

    def test_timezone_default(self):
        req = CreateScheduleRequest(
            function_name="my-func",
            cron_expression="0 * * * *",
            failure_policy={"strategy": "continue"},
        )
        assert req.timezone == "UTC"

    def test_short_cron_rejected(self):
        with pytest.raises(ValidationError):
            CreateScheduleRequest(
                function_name="f",
                cron_expression="* *",
                failure_policy={"strategy": "continue"},
            )


class TestCreateWebhookRequest:
    def test_valid_path(self):
        req = CreateWebhookRequest(path="events", handler_function_name="handler")
        assert req.path == "events"

    def test_path_strips_slashes(self):
        req = CreateWebhookRequest(path="/events/", handler_function_name="handler")
        assert req.path == "events"

    def test_nested_path(self):
        req = CreateWebhookRequest(path="github/push", handler_function_name="handler")
        assert req.path == "github/push"

    def test_path_with_hyphens(self):
        req = CreateWebhookRequest(path="my-events", handler_function_name="handler")
        assert req.path == "my-events"

    def test_invalid_path_special_chars(self):
        with pytest.raises(ValidationError, match="Path"):
            CreateWebhookRequest(path="ev@nts", handler_function_name="handler")

    def test_secret_optional(self):
        req = CreateWebhookRequest(path="events", handler_function_name="handler")
        assert req.secret is None

    def test_secret_set(self):
        val = "s3cr3t"  # pragma: allowlist secret
        req = CreateWebhookRequest(path="events", handler_function_name="h", secret=val)
        assert req.secret == val


class TestConfigureAIRequest:
    def test_valid_anthropic(self):
        key = "sk-ant-123"  # pragma: allowlist secret
        req = ConfigureAIRequest(engine="anthropic", model="claude-3-opus", api_key=key)
        assert req.engine == "anthropic"

    def test_valid_openai(self):
        req = ConfigureAIRequest(engine="openai", model="gpt-4", api_key="sk-123")
        assert req.engine == "openai"

    def test_valid_google(self):
        req = ConfigureAIRequest(engine="google", model="gemini-pro", api_key="key")
        assert req.engine == "google"

    def test_valid_openrouter(self):
        req = ConfigureAIRequest(
            engine="openrouter", model="meta/llama", api_key="key"
        )  # pragma: allowlist secret
        assert req.engine == "openrouter"

    def test_invalid_engine_rejected(self):
        with pytest.raises(ValidationError, match="engine"):
            ConfigureAIRequest(
                engine="bedrock", model="model", api_key="key"
            )  # pragma: allowlist secret

    def test_system_prompt_optional(self):
        req = ConfigureAIRequest(engine="openai", model="gpt-4", api_key="sk")
        assert req.system_prompt is None


class TestCreateChannelRequest:
    @pytest.mark.parametrize("channel_type", ["discord", "slack", "whatsapp", "email"])
    def test_valid_channel_types(self, channel_type):
        req = CreateChannelRequest(channel_type=channel_type, config={"token": "abc"})
        assert req.channel_type == channel_type

    def test_invalid_channel_type_rejected(self):
        with pytest.raises(ValidationError, match="channel_type"):
            CreateChannelRequest(channel_type="telegram", config={})


class TestSetStateRequest:
    def test_string_value(self):
        req = SetStateRequest(value="hello")
        assert req.value == "hello"

    def test_dict_value(self):
        req = SetStateRequest(value={"key": "val"})
        assert req.value == {"key": "val"}

    def test_none_value(self):
        req = SetStateRequest(value=None)
        assert req.value is None

    def test_list_value(self):
        req = SetStateRequest(value=[1, 2, 3])
        assert req.value == [1, 2, 3]


class TestCloneAgentRequest:
    def test_valid_name(self):
        req = CloneAgentRequest(new_name="clone-1")
        assert req.new_name == "clone-1"

    def test_lowercased(self):
        req = CloneAgentRequest(new_name="Clone1")
        assert req.new_name == "clone1"

    def test_invalid_name_rejected(self):
        with pytest.raises(ValidationError, match="alphanumeric"):
            CloneAgentRequest(new_name="-bad")
