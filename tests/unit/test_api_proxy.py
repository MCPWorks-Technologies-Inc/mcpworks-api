"""Unit tests for API proxy pure logic — credential injection + path building (019)."""

import pytest

from mcpworks_api.core.api_proxy import _apply_injections, _build_path

# --------------------------------------------------------------------------- paths


def test_build_path_substitutes_params() -> None:
    assert _build_path("/orders/{id}", {"id": "o_1"}) == "/orders/o_1"
    assert _build_path("/a/{x}/b/{y}", {"x": "1", "y": "2"}) == "/a/1/b/2"


def test_build_path_missing_param_raises() -> None:
    with pytest.raises(KeyError):
        _build_path("/orders/{id}", {})


def test_build_path_no_params() -> None:
    assert _build_path("/orders", {}) == "/orders"


# --------------------------------------------------------------------- injections


def test_stored_header_injection() -> None:
    headers: dict = {}
    query: dict = {}
    auth = [
        {
            "name": "api_key",
            "location": "header",
            "key": "X-API-Key",
            "format": "{value}",
            "source": "stored",
        }
    ]
    missing = _apply_injections(auth, {"api_key": "sk_live_1"}, {}, headers, query)
    assert missing is None
    assert headers["X-API-Key"] == "sk_live_1"
    assert query == {}


def test_bearer_injection_formats_and_no_double_prefix() -> None:
    headers: dict = {}
    auth = [{"name": "t", "location": "bearer", "format": "Bearer {value}", "source": "stored"}]
    _apply_injections(auth, {"t": "abc"}, {}, headers, {})
    assert headers["Authorization"] == "Bearer abc"

    # If the format already yields a 'Bearer ' prefix, it must not be doubled.
    headers2: dict = {}
    _apply_injections(
        [{"name": "t", "location": "bearer", "format": "{value}", "source": "stored"}],
        {"t": "Bearer xyz"},
        {},
        headers2,
        {},
    )
    assert headers2["Authorization"] == "Bearer xyz"


def test_query_injection() -> None:
    query: dict = {}
    auth = [
        {
            "name": "key",
            "location": "query",
            "key": "api_key",
            "format": "{value}",
            "source": "stored",
        }
    ]
    _apply_injections(auth, {"key": "Q1"}, {}, {}, query)
    assert query["api_key"] == "Q1"


def test_basic_injection() -> None:
    headers: dict = {}
    auth = [{"name": "b", "location": "basic", "format": "{value}", "source": "stored"}]
    _apply_injections(auth, {"b": "dXNlcjpwYXNz"}, {}, headers, {})
    assert headers["Authorization"] == "Basic dXNlcjpwYXNz"


def test_passthrough_injection_from_env() -> None:
    headers: dict = {}
    auth = [
        {
            "name": "token",
            "location": "bearer",
            "format": "Bearer {value}",
            "source": "passthrough",
            "env_var": "ACME_TOKEN",
        }
    ]
    missing = _apply_injections(auth, {}, {"ACME_TOKEN": "usr_tok"}, headers, {})
    assert missing is None
    assert headers["Authorization"] == "Bearer usr_tok"


def test_missing_stored_credential_returns_name() -> None:
    missing = _apply_injections(
        [{"name": "api_key", "location": "header", "key": "X", "source": "stored"}],
        {},  # no secret
        {},
        {},
        {},
    )
    assert missing == "api_key"


def test_missing_passthrough_credential_returns_name() -> None:
    missing = _apply_injections(
        [{"name": "token", "location": "bearer", "source": "passthrough", "env_var": "ACME_TOKEN"}],
        {},
        {},  # env var absent
        {},
        {},
    )
    assert missing == "token"


def test_mixed_injections_all_applied() -> None:
    headers: dict = {}
    query: dict = {}
    auth = [
        {
            "name": "k",
            "location": "header",
            "key": "X-Key",
            "format": "{value}",
            "source": "stored",
        },
        {
            "name": "t",
            "location": "bearer",
            "format": "Bearer {value}",
            "source": "passthrough",
            "env_var": "TOK",
        },
    ]
    missing = _apply_injections(auth, {"k": "kv"}, {"TOK": "tv"}, headers, query)
    assert missing is None
    assert headers["X-Key"] == "kv"
    assert headers["Authorization"] == "Bearer tv"
