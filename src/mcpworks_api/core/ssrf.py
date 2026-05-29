"""SSRF defense for user-supplied API base URLs (feature 019).

The largest new attack surface vs 008: base URLs are user-controlled, so a
registered API could point (or be rebound via DNS) at internal/cloud-metadata
addresses. We defend by resolving the hostname to ALL its addresses and rejecting
if ANY resolves into a denied range — evaluated at *call time*, not just at
registration, which is what defeats DNS rebinding.

Public API:
    SSRFError                       — raised when a target is disallowed
    ip_is_denied(ip_str)            — pure predicate over a literal address
    resolve_and_validate(host, ...) — async; returns vetted addresses or raises
    assert_url_allowed(url, ...)    — async; validates scheme + host of a URL

The resolver is injectable so callers (and tests) can control DNS. Production
uses the event loop's getaddrinfo.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Extra ranges not flagged by the ipaddress boolean properties below.
_EXTRA_DENIED = [
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT (RFC 6598)
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking (RFC 2544)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("64:ff9b::/96"),  # NAT64
]

Resolver = Callable[[str], Awaitable[list[str]]]


class SSRFError(Exception):
    """Raised when a target host/URL is disallowed by the SSRF policy."""


def _addr_is_denied(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if an address object falls in any denied range."""
    # Unwrap IPv4-mapped IPv6 (::ffff:a.b.c.d) and re-check the embedded IPv4.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _addr_is_denied(addr.ipv4_mapped)

    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        return True

    return any(addr in net for net in _EXTRA_DENIED)


def ip_is_denied(ip_str: str) -> bool:
    """Pure predicate: is this literal IP address in a denied range?

    Unparseable input is treated as denied (fail closed).
    """
    try:
        return _addr_is_denied(ipaddress.ip_address(ip_str))
    except ValueError:
        return True


async def _default_resolver(host: str) -> list[str]:
    """Resolve a hostname to all A/AAAA addresses via the event loop."""
    import asyncio

    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    # getaddrinfo returns (family, type, proto, canonname, sockaddr); sockaddr[0] is the IP.
    return [str(info[4][0]) for info in infos]


async def resolve_and_validate(
    host: str,
    resolver: Resolver | None = None,
) -> list[str]:
    """Resolve ``host`` and return its vetted addresses, or raise SSRFError.

    If the host is already an IP literal it is validated directly. Otherwise it
    is resolved to every address and rejected if ANY address is denied (blocks
    split-horizon and rebinding tricks).
    """
    # IP literal? validate directly (strip IPv6 brackets).
    literal = host.strip("[]")
    try:
        ipaddress.ip_address(literal)
        if _addr_is_denied(ipaddress.ip_address(literal)):
            raise SSRFError(f"host resolves to a denied address: {literal}")
        return [literal]
    except ValueError:
        pass  # not a literal — resolve it

    resolve = resolver or _default_resolver
    try:
        addresses = await resolve(host)
    except SSRFError:
        raise
    except Exception as e:  # DNS failure
        raise SSRFError(f"could not resolve host '{host}': {e}") from e

    if not addresses:
        raise SSRFError(f"host '{host}' did not resolve to any address")

    for addr in addresses:
        if ip_is_denied(addr):
            raise SSRFError(f"host '{host}' resolves to a denied address: {addr}")

    return addresses


async def assert_url_allowed(url: str, resolver: Resolver | None = None) -> list[str]:
    """Validate a URL's scheme and host against the SSRF policy.

    Returns the vetted resolved addresses (useful for connection pinning).
    Raises SSRFError on any violation.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFError(f"scheme '{parts.scheme}' not allowed (only http/https)")
    host = parts.hostname
    if not host:
        raise SSRFError("URL has no host")
    return await resolve_and_validate(host, resolver=resolver)
