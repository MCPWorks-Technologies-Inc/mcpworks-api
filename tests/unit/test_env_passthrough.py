"""Unit tests for env_passthrough module.

Covers all 17 test cases from spec Section 10.1 plus integration tests.
"""

import base64
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Load env_passthrough directly from file to avoid mcp/__init__.py pulling in
# transport.py which requires the external `mcp` SDK (not installed in test env).
_src = Path(__file__).resolve().parents[2] / "src" / "mcpworks_api" / "mcp" / "env_passthrough.py"
_spec = importlib.util.spec_from_file_location("env_passthrough", _src)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["env_passthrough"] = _mod
_spec.loader.exec_module(_mod)

BLOCKED_EXACT = _mod.BLOCKED_EXACT
BLOCKED_PREFIXES = _mod.BLOCKED_PREFIXES
HEADER_NAME = _mod.HEADER_NAME
MAX_DECODED_BYTES = _mod.MAX_DECODED_BYTES
MAX_KEY_COUNT = _mod.MAX_KEY_COUNT
MAX_VALUE_BYTES = _mod.MAX_VALUE_BYTES
RESERVED_PREFIX = _mod.RESERVED_PREFIX
EnvPassthroughError = _mod.EnvPassthroughError
check_required_env = _mod.check_required_env
extract_env_vars = _mod.extract_env_vars
filter_env_for_function = _mod.filter_env_for_function


def _make_request(env_dict: dict | None = None, raw_header: str | None = None):
    """Build a mock Starlette Request with the X-MCPWorks-Env header."""
    request = MagicMock()
    if raw_header is not None:
        request.headers = {HEADER_NAME: raw_header}
    elif env_dict is not None:
        encoded = base64.b64encode(json.dumps(env_dict).encode()).decode()
        request.headers = {HEADER_NAME: encoded}
    else:
        request.headers = {}
    return request


class TestExtractEnvVars:
    def test_valid_base64_json(self):
        env = {"API_KEY": "sk-123", "SECRET": "abc"}
        result = extract_env_vars(_make_request(env))
        assert result == {"API_KEY": "sk-123", "SECRET": "abc"}

    def test_invalid_base64(self):
        request = _make_request(raw_header="not-valid-base64!!!")
        with pytest.raises(EnvPassthroughError, match="not valid base64"):
            extract_env_vars(request)

    def test_valid_base64_invalid_json(self):
        raw = base64.b64encode(b"not json at all").decode()
        request = _make_request(raw_header=raw)
        with pytest.raises(EnvPassthroughError, match="not valid JSON"):
            extract_env_vars(request)

    def test_payload_too_large(self):
        big = {"KEY": "x" * (MAX_DECODED_BYTES + 1)}
        encoded = base64.b64encode(json.dumps(big).encode()).decode()
        request = _make_request(raw_header=encoded)
        with pytest.raises(EnvPassthroughError, match="too large"):
            extract_env_vars(request)

    def test_too_many_keys(self):
        env = {f"KEY{i:03d}": "v" for i in range(MAX_KEY_COUNT + 1)}
        with pytest.raises(EnvPassthroughError, match="Too many env vars"):
            extract_env_vars(_make_request(env))

    def test_blocked_exact_name(self):
        for name in ("PATH", "HOME", "SHELL"):
            with pytest.raises(EnvPassthroughError, match="blocked"):
                extract_env_vars(_make_request({name: "val"}))

    def test_blocked_prefix(self):
        for name in ("LD_PRELOAD", "PYTHONPATH", "NSJAIL_CFG", "SSL_CERT_FILE"):
            with pytest.raises(EnvPassthroughError, match="blocked"):
                extract_env_vars(_make_request({name: "val"}))

    def test_reserved_prefix(self):
        with pytest.raises(EnvPassthroughError, match="reserved for platform"):
            extract_env_vars(_make_request({"MCPWORKS_SECRET": "val"}))

    def test_invalid_key_format(self):
        for bad_key in ("lowercase", "123START", "HAS SPACE", "A" * 200):
            with pytest.raises(EnvPassthroughError, match="Invalid env var name"):
                extract_env_vars(_make_request({bad_key: "val"}))

    def test_value_too_large(self):
        env = {"BIG_VAL": "x" * (MAX_VALUE_BYTES + 1)}
        with pytest.raises(EnvPassthroughError, match="value too large"):
            extract_env_vars(_make_request(env))

    def test_null_byte_in_value(self):
        env = {"HAS_NULL": "before\x00after"}
        with pytest.raises(EnvPassthroughError, match="null byte"):
            extract_env_vars(_make_request(env))

    def test_absent_header(self):
        request = _make_request()
        assert extract_env_vars(request) == {}

    def test_non_string_value(self):
        raw = base64.b64encode(json.dumps({"NUM": 42}).encode()).decode()
        request = _make_request(raw_header=raw)
        with pytest.raises(EnvPassthroughError, match="must be a string"):
            extract_env_vars(request)

    def test_non_dict_payload(self):
        raw = base64.b64encode(json.dumps(["a", "b"]).encode()).decode()
        request = _make_request(raw_header=raw)
        with pytest.raises(EnvPassthroughError, match="must be a JSON object"):
            extract_env_vars(request)

    def test_empty_header_value(self):
        request = MagicMock()
        request.headers = {HEADER_NAME: ""}
        assert extract_env_vars(request) == {}

    def test_valid_single_var(self):
        result = extract_env_vars(_make_request({"OPENAI_API_KEY": "sk-test"}))
        assert result == {"OPENAI_API_KEY": "sk-test"}


class TestFilterEnvForFunction:
    def test_filter_with_required_env(self):
        env = {"A": "1", "B": "2", "C": "3"}
        result = filter_env_for_function(env, required_env=["A", "B"], optional_env=None)
        assert result == {"A": "1", "B": "2"}

    def test_filter_with_optional_env(self):
        env = {"A": "1", "B": "2"}
        result = filter_env_for_function(env, required_env=None, optional_env=["B", "C"])
        assert result == {"B": "2"}

    def test_filter_with_both(self):
        env = {"A": "1", "B": "2", "C": "3"}
        result = filter_env_for_function(env, required_env=["A"], optional_env=["C"])
        assert result == {"A": "1", "C": "3"}

    def test_no_declarations_returns_empty(self):
        env = {"A": "1", "B": "2"}
        result = filter_env_for_function(env, required_env=None, optional_env=None)
        assert result == {}

    def test_empty_env_returns_empty(self):
        result = filter_env_for_function({}, required_env=["A"], optional_env=None)
        assert result == {}

    def test_undeclared_vars_dropped(self):
        env = {"A": "1", "EXTRA": "dropped"}
        result = filter_env_for_function(env, required_env=["A"], optional_env=None)
        assert result == {"A": "1"}
        assert "EXTRA" not in result


class TestCheckRequiredEnv:
    def test_all_present(self):
        env = {"A": "1", "B": "2"}
        missing = check_required_env(env, required_env=["A", "B"])
        assert missing == []

    def test_missing_required(self):
        env = {"A": "1"}
        missing = check_required_env(env, required_env=["A", "B", "C"])
        assert sorted(missing) == ["B", "C"]

    def test_no_required_env(self):
        assert check_required_env({"A": "1"}, required_env=None) == []
        assert check_required_env({"A": "1"}, required_env=[]) == []

    def test_empty_env_all_missing(self):
        missing = check_required_env({}, required_env=["A", "B"])
        assert sorted(missing) == ["A", "B"]


class TestIntegration:
    """Integration tests: filter + check together."""

    def test_full_pipeline_happy_path(self):
        env = {"A": "1", "B": "2", "EXTRA": "nope"}
        filtered = filter_env_for_function(env, required_env=["A"], optional_env=["B"])
        missing = check_required_env(filtered, required_env=["A"])
        assert filtered == {"A": "1", "B": "2"}
        assert missing == []

    def test_full_pipeline_missing_required(self):
        env = {"B": "2"}
        filtered = filter_env_for_function(env, required_env=["A"], optional_env=["B"])
        missing = check_required_env(filtered, required_env=["A"])
        assert filtered == {"B": "2"}
        assert missing == ["A"]

    def test_full_pipeline_no_declarations(self):
        env = {"A": "1"}
        filtered = filter_env_for_function(env, required_env=None, optional_env=None)
        missing = check_required_env(filtered, required_env=None)
        assert filtered == {}
        assert missing == []


class TestBlocklistCompleteness:
    """Verify all documented blocked names are enforced."""

    def test_all_blocked_exact_names(self):
        for name in BLOCKED_EXACT:
            with pytest.raises(EnvPassthroughError):
                extract_env_vars(_make_request({name: "val"}))

    def test_all_blocked_prefixes(self):
        for prefix in BLOCKED_PREFIXES:
            test_name = prefix + "TEST"
            with pytest.raises(EnvPassthroughError):
                extract_env_vars(_make_request({test_name: "val"}))

    def test_mcpworks_internal_blocked(self):
        with pytest.raises(EnvPassthroughError):
            extract_env_vars(_make_request({"MCPWORKS_INTERNAL_TOKEN": "val"}))
