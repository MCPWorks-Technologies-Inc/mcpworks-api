"""Unit tests for the SSRF gate (feature 019, T010)."""

import pytest

from mcpworks_api.core.ssrf import (
    SSRFError,
    assert_url_allowed,
    ip_is_denied,
    resolve_and_validate,
)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.5.5.5",
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "169.254.0.1",
        "0.0.0.0",
        "100.64.0.1",  # CGNAT
        "198.18.0.1",  # benchmarking
        "224.0.0.1",  # multicast
        "::1",  # IPv6 loopback
        "fe80::1",  # IPv6 link-local
        "fc00::1",  # IPv6 unique-local
        "::ffff:169.254.169.254",  # IPv4-mapped metadata
        "::ffff:10.0.0.1",  # IPv4-mapped private
        "not-an-ip",  # fail closed
    ],
)
def test_denied_addresses(ip: str) -> None:
    assert ip_is_denied(ip) is True


@pytest.mark.parametrize(
    "ip",
    ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"],
)
def test_allowed_public_addresses(ip: str) -> None:
    assert ip_is_denied(ip) is False


async def _resolver_to(addrs: list[str]):
    async def _r(_host: str) -> list[str]:
        return addrs

    return _r


@pytest.mark.asyncio
async def test_public_host_passes() -> None:
    resolver = await _resolver_to(["93.184.216.34"])
    out = await resolve_and_validate("example.com", resolver=resolver)
    assert out == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_dns_rebinding_blocked() -> None:
    # Hostname looks innocuous but resolves to a private address at call time.
    resolver = await _resolver_to(["10.0.0.5"])
    with pytest.raises(SSRFError):
        await resolve_and_validate("rebind.attacker.example", resolver=resolver)


@pytest.mark.asyncio
async def test_split_horizon_any_denied_blocks() -> None:
    # One public, one private — must block (any denied → deny).
    resolver = await _resolver_to(["93.184.216.34", "127.0.0.1"])
    with pytest.raises(SSRFError):
        await resolve_and_validate("split.example", resolver=resolver)


@pytest.mark.asyncio
async def test_ip_literal_denied() -> None:
    with pytest.raises(SSRFError):
        await resolve_and_validate("169.254.169.254")


@pytest.mark.asyncio
async def test_ip_literal_public_ok() -> None:
    out = await resolve_and_validate("8.8.8.8")
    assert out == ["8.8.8.8"]


@pytest.mark.asyncio
async def test_assert_url_scheme_rejected() -> None:
    with pytest.raises(SSRFError):
        await assert_url_allowed("file:///etc/passwd")
    with pytest.raises(SSRFError):
        await assert_url_allowed("ftp://example.com/x")


@pytest.mark.asyncio
async def test_assert_url_allowed_public() -> None:
    resolver = await _resolver_to(["93.184.216.34"])
    out = await assert_url_allowed("https://api.example.com/openapi.json", resolver=resolver)
    assert out == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_assert_url_denied_host() -> None:
    resolver = await _resolver_to(["10.1.2.3"])
    with pytest.raises(SSRFError):
        await assert_url_allowed("https://internal.example.com/x", resolver=resolver)
