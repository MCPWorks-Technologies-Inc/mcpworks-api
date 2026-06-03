"""Unit tests for ApiServerService pure logic — auth splitting / redaction (019)."""

import pytest

from mcpworks_api.core.exceptions import ValidationError
from mcpworks_api.services.api_server import ApiServerService


def test_split_auth_separates_stored_secret_from_definition() -> None:
    auth = [
        {
            "name": "api_key",
            "location": "header",
            "key": "X-API-Key",
            "format": "{value}",
            "source": "stored",
            "value": "sk_live_secret",
        }
    ]
    definitions, secrets = ApiServerService._split_auth(auth)
    # Secret value extracted into the secrets map...
    assert secrets == {"api_key": "sk_live_secret"}
    # ...and absent from the stored definition (structural redaction).
    assert len(definitions) == 1
    assert "value" not in definitions[0]
    assert definitions[0]["source"] == "stored"
    assert definitions[0]["key"] == "X-API-Key"


def test_split_auth_passthrough_keeps_env_var_no_secret() -> None:
    auth = [
        {
            "name": "token",
            "location": "bearer",
            "format": "Bearer {value}",
            "source": "passthrough",
            "env_var": "ACME_TOKEN",
        }
    ]
    definitions, secrets = ApiServerService._split_auth(auth)
    assert secrets == {}  # passthrough never stores a value
    assert definitions[0]["env_var"] == "ACME_TOKEN"
    assert "value" not in definitions[0]


def test_split_auth_mixed_sources() -> None:
    auth = [
        {"name": "k", "location": "header", "key": "X", "source": "stored", "value": "v"},
        {"name": "t", "location": "bearer", "source": "passthrough", "env_var": "T"},
    ]
    definitions, secrets = ApiServerService._split_auth(auth)
    assert secrets == {"k": "v"}
    assert {d["name"] for d in definitions} == {"k", "t"}


def test_split_auth_stored_without_value_raises() -> None:
    with pytest.raises(ValidationError):
        ApiServerService._split_auth(
            [{"name": "k", "location": "header", "key": "X", "source": "stored"}]
        )


def test_split_auth_passthrough_without_env_var_raises() -> None:
    with pytest.raises(ValidationError):
        ApiServerService._split_auth([{"name": "t", "location": "bearer", "source": "passthrough"}])


def test_split_auth_invalid_location_raises() -> None:
    with pytest.raises(ValidationError):
        ApiServerService._split_auth(
            [{"name": "x", "location": "cookie", "source": "stored", "value": "v"}]
        )


def test_split_auth_invalid_source_raises() -> None:
    with pytest.raises(ValidationError):
        ApiServerService._split_auth(
            [{"name": "x", "location": "header", "source": "oauth2", "value": "v"}]
        )


def test_split_auth_empty() -> None:
    definitions, secrets = ApiServerService._split_auth(None)
    assert definitions == []
    assert secrets == {}
