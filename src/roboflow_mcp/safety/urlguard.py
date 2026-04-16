"""SSRF defense for URL-based image ingestion.

When an MCP tool accepts a URL to fetch (Phase 1: upload-from-URL), we have
to prevent an LLM-controlled URL from pointing at internal services the
server process can reach: cloud metadata endpoints (169.254.169.254 on
AWS/GCP/Azure), kubelet API, internal HTTP services, localhost, SSH, etc.

This module:

1. Enforces a scheme allowlist (``https`` by default; ``http`` only when
   the operator has set ``ROBOFLOW_MCP_ALLOW_INSECURE=1``).
2. Resolves the hostname via DNS and rejects any reply that contains an IP
   in a blocked range (RFC1918, loopback, link-local, cloud metadata,
   multicast, reserved).
3. Streams the response with an explicit byte cap and timeout so a
   cooperative-looking URL can't exhaust memory.

Residual risk: a DNS rebinding attack between our ``getaddrinfo`` call and
httpx's internal resolution can swing the IP under us. Closing that window
needs a custom httpx ``AsyncBaseTransport`` that pins the IP after the
initial lookup and is being deferred to v0.5. The current guard still
catches the attack class nearly all real SSRF exploits land in, and is
documented in ``docs/SECURITY_MODEL.md`` as threat T3 (partial mitigation
today, full in v0.5).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from ..errors import UrlGuardError

_DEFAULT_MAX_BYTES = 25 * 1024 * 1024  # 25 MiB
_DEFAULT_TIMEOUT_S = 30.0
_ALLOWED_SCHEMES = frozenset({"https"})
_ALLOWED_SCHEMES_INSECURE = frozenset({"https", "http"})

# Well-known single-IP targets we always want to block regardless of range.
_FORBIDDEN_IPS = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure metadata
        ipaddress.ip_address("169.254.170.2"),  # ECS task metadata
        ipaddress.ip_address("fd00:ec2::254"),  # AWS IMDSv2 IPv6
    }
)


@dataclass(frozen=True)
class FetchResult:
    """Result of a guarded URL fetch."""

    content: bytes
    content_type: str
    final_url: str


def _is_blocked_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> tuple[bool, str]:
    """Return (blocked, reason) for an IP. Reason is empty when allowed.

    Ordering matters: several ranges overlap in ``ipaddress``'s
    classification (``169.254.0.0/16`` is both ``is_link_local`` and
    ``is_private`` in Python 3.12+, and ``::`` is both ``is_unspecified``
    and ``is_private``). We check the more-specific range first so error
    messages are accurate.
    """
    if ip in _FORBIDDEN_IPS:
        return True, f"{ip} is a cloud metadata endpoint"
    if ip.is_unspecified:
        return True, f"{ip} is the unspecified address"
    if ip.is_loopback:
        return True, f"{ip} is loopback"
    if ip.is_link_local:
        return True, f"{ip} is link-local"
    if ip.is_multicast:
        return True, f"{ip} is multicast"
    if ip.is_reserved:
        return True, f"{ip} is IANA-reserved"
    if ip.is_private:
        return True, f"{ip} is a private-network address"
    return False, ""


async def _resolve_host(
    hostname: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Return every IP address DNS currently associates with ``hostname``.

    Runs in a thread because ``socket.getaddrinfo`` is blocking.
    """
    loop = asyncio.get_running_loop()
    infos = await loop.run_in_executor(
        None,
        lambda: socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM),
    )
    addrs: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for _family, _type, _proto, _canon, sockaddr in infos:
        # sockaddr is (host, port) for IPv4, (host, port, flow, scope) for IPv6
        host = sockaddr[0]
        try:
            addrs.append(ipaddress.ip_address(host))
        except ValueError:  # pragma: no cover - getaddrinfo always gives valid IPs
            continue
    return addrs


def _validate_scheme(scheme: str, *, allow_insecure: bool) -> None:
    allowed = _ALLOWED_SCHEMES_INSECURE if allow_insecure else _ALLOWED_SCHEMES
    if scheme.lower() not in allowed:
        raise UrlGuardError(
            f"URL scheme {scheme!r} is not allowed. "
            f"Permitted: {sorted(allowed)}. "
            "Set ROBOFLOW_MCP_ALLOW_INSECURE=1 for dev-only http:// access."
        )


async def validate_url(url: str, *, allow_insecure: bool = False) -> str:
    """Validate a URL for SSRF-safety and return the hostname.

    Raises :class:`UrlGuardError` when the scheme is wrong, the hostname is
    missing, or any IP the hostname resolves to is in a blocked range.
    """
    parsed = urlparse(url)
    # Check scheme first so that a bogus URL like ``file:///etc/passwd``
    # surfaces as a scheme error rather than a hostname one — that's the
    # more actionable message for a caller who built the URL wrong.
    _validate_scheme(parsed.scheme, allow_insecure=allow_insecure)
    if not parsed.hostname:
        raise UrlGuardError(f"URL {url!r} has no hostname")

    # Reject credential-bearing URLs outright — they usually indicate either
    # an accidentally-committed secret or an SSRF attempt to confuse the
    # resolver via userinfo.
    if parsed.username or parsed.password:
        raise UrlGuardError("URLs with embedded credentials are not allowed.")

    try:
        addrs = await _resolve_host(parsed.hostname)
    except socket.gaierror as exc:
        raise UrlGuardError(
            f"DNS lookup failed for {parsed.hostname!r}: {exc}"
        ) from exc

    if not addrs:
        raise UrlGuardError(f"No IPs resolved for {parsed.hostname!r}")

    for ip in addrs:
        blocked, reason = _is_blocked_ip(ip)
        if blocked:
            raise UrlGuardError(
                f"Hostname {parsed.hostname!r} resolves to a blocked address: {reason}"
            )

    return parsed.hostname


async def fetch_bytes_safely(
    url: str,
    *,
    allow_insecure: bool = False,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> FetchResult:
    """Validate ``url`` then stream its body up to ``max_bytes``.

    A fresh ``httpx.AsyncClient`` is always constructed internally so that
    ``follow_redirects=False`` is guaranteed — we do *not* accept an
    externally-supplied client. A 301/302 to a private IP would defeat the
    DNS-side SSRF guard, so the client construction is deliberately kept
    inside this function.
    """
    await validate_url(url, allow_insecure=allow_insecure)

    async with (
        httpx.AsyncClient(
            timeout=timeout_s,
            follow_redirects=False,
            verify=True,
        ) as client,
        client.stream("GET", url, timeout=timeout_s) as response,
    ):
        if response.status_code >= 400:
            raise UrlGuardError(
                f"Fetch failed: HTTP {response.status_code} for {url}"
            )
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = None
            if declared is not None and declared > max_bytes:
                raise UrlGuardError(
                    f"Remote resource advertises {declared} bytes, "
                    f"exceeds {max_bytes} cap."
                )

        content_type = response.headers.get(
            "content-type", "application/octet-stream"
        )
        buf = bytearray()
        async for chunk in response.aiter_bytes():
            if len(buf) + len(chunk) > max_bytes:
                raise UrlGuardError(
                    f"Response exceeds {max_bytes} bytes during stream."
                )
            buf.extend(chunk)

        return FetchResult(
            content=bytes(buf),
            content_type=content_type.split(";")[0].strip(),
            final_url=str(response.url),
        )
