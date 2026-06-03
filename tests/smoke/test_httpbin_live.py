"""Live smoke test for API → MCP against httpbin.org (feature 019).

Exercises the importer, the SSRF gate, and the proxy's request-construction +
credential-injection helpers against a REAL public API — no DB or sandbox needed.
httpbin echoes requests back, so we can assert that injected credentials, query
params, and path templating actually reach the upstream.

Makes real outbound network calls. SKIPPED by default; enable with:

    RUN_LIVE_TESTS=1 pytest tests/smoke/test_httpbin_live.py -m network

Marked ``network`` so it can also be deselected with ``-m "not network"``.
"""

import os

import httpx
import pytest

from mcpworks_api.core.api_proxy import _apply_injections, _build_path
from mcpworks_api.core.openapi_import import extract_endpoints, parse_spec
from mcpworks_api.core.ssrf import SSRFError, assert_url_allowed

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        not os.getenv("RUN_LIVE_TESTS"),
        reason="live network test; set RUN_LIVE_TESTS=1 to run",
    ),
]

BASE = "https://httpbin.org"
TIMEOUT = 15


async def test_import_real_openapi_spec() -> None:
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as c:
        spec_text = (await c.get(f"{BASE}/spec.json")).text
    result = extract_endpoints(parse_spec(spec_text))
    # httpbin's spec has dozens of operations across shared paths (collision handling).
    assert result.total_discovered > 30
    ops = {e.operation_id: e for e in result.endpoints}
    # Same path, multiple verbs → distinct operation_ids (derivation + no collision).
    assert "get_anything" in ops
    assert "post_anything" in ops
    assert ops["get_anything"].method == "GET"


async def test_ssrf_gate_allows_public_blocks_private() -> None:
    ips = await assert_url_allowed(f"{BASE}/get")
    assert ips, "public host should resolve to at least one allowed address"
    for bad in (
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
        "http://10.0.0.1/x",  # private
        "http://localhost/x",  # loopback
    ):
        with pytest.raises(SSRFError):
            await assert_url_allowed(bad)


async def test_stored_bearer_injection_authenticates() -> None:
    headers: dict = {}
    query: dict = {}
    auth = [{"name": "token", "location": "bearer", "format": "Bearer {value}", "source": "stored"}]
    missing = _apply_injections(auth, {"token": "sk_test_ABC123"}, {}, headers, query)
    assert missing is None
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as c:
        resp = await c.get(f"{BASE}{_build_path('/bearer', {})}", headers=headers)
    body = resp.json()
    assert resp.status_code == 200
    assert body["authenticated"] is True
    assert body["token"] == "sk_test_ABC123"


async def test_path_template_and_query_injection_reach_upstream() -> None:
    headers: dict = {}
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
    _apply_injections(auth, {"key": "QKEY9"}, {}, headers, query)
    path = _build_path("/anything/{id}", {"id": "order_42"})
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as c:
        echo = (await c.get(f"{BASE}{path}", params={**query, "status": "open"})).json()
    assert echo["url"].endswith("/anything/order_42?api_key=QKEY9&status=open")
    assert echo["args"] == {"api_key": "QKEY9", "status": "open"}


async def test_passthrough_header_reaches_upstream() -> None:
    headers: dict = {}
    auth = [
        {
            "name": "api",
            "location": "header",
            "key": "X-Api-Key",
            "format": "{value}",
            "source": "passthrough",
            "env_var": "ACME",
        }
    ]
    # Passthrough value comes from the (simulated) execution env, not sandbox code.
    _apply_injections(auth, {}, {"ACME": "passthru_TOKEN"}, headers, {})
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as c:
        echo = (await c.get(f"{BASE}/headers", headers=headers)).json()
    assert echo["headers"].get("X-Api-Key") == "passthru_TOKEN"
