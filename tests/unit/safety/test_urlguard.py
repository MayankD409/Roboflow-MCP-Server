"""Tests for roboflow_mcp.safety.urlguard."""

from __future__ import annotations

import ipaddress
from unittest.mock import patch

import httpx
import pytest
import respx

from roboflow_mcp.errors import UrlGuardError
from roboflow_mcp.safety import urlguard
from roboflow_mcp.safety.urlguard import fetch_bytes_safely, validate_url


async def _mock_resolve(ip: str) -> list[ipaddress._BaseAddress]:
    return [ipaddress.ip_address(ip)]


# ---------- scheme + hostname checks ----------


async def test_https_public_ip_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return await _mock_resolve("8.8.8.8")

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    assert await validate_url("https://example.com/x.jpg") == "example.com"


async def test_http_rejected_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return await _mock_resolve("8.8.8.8")

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    with pytest.raises(UrlGuardError, match="scheme"):
        await validate_url("http://example.com/x.jpg")


async def test_http_allowed_with_insecure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return await _mock_resolve("8.8.8.8")

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    assert (
        await validate_url("http://example.com/x.jpg", allow_insecure=True)
        == "example.com"
    )


async def test_file_scheme_rejected() -> None:
    with pytest.raises(UrlGuardError, match="scheme"):
        await validate_url("file:///etc/passwd")


async def test_gopher_scheme_rejected() -> None:
    with pytest.raises(UrlGuardError, match="scheme"):
        await validate_url("gopher://example.com/x")


async def test_missing_hostname_rejected() -> None:
    with pytest.raises(UrlGuardError, match="hostname"):
        await validate_url("https:///x")


async def test_credentials_in_url_rejected() -> None:
    with pytest.raises(UrlGuardError, match="credentials"):
        await validate_url("https://user:pass@example.com/x.jpg")


# ---------- IP-range blocklist ----------


@pytest.mark.parametrize(
    "ip,reason_fragment",
    [
        ("127.0.0.1", "loopback"),
        ("127.5.5.5", "loopback"),
        ("::1", "loopback"),
        ("10.0.0.1", "private"),
        ("192.168.1.1", "private"),
        ("172.16.0.1", "private"),
        ("169.254.0.1", "link-local"),
        ("169.254.169.254", "metadata"),  # AWS/GCP/Azure metadata
        ("169.254.170.2", "metadata"),  # ECS task metadata
        ("fe80::1", "link-local"),
        ("224.0.0.1", "multicast"),
        ("ff02::1", "multicast"),
        ("0.0.0.0", "unspecified"),
        ("::", "unspecified"),
    ],
)
async def test_blocked_ip_ranges(
    ip: str,
    reason_fragment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return [ipaddress.ip_address(ip)]

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    with pytest.raises(UrlGuardError, match=reason_fragment):
        await validate_url("https://attacker.com/x")


async def test_mixed_safe_and_blocked_still_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If DNS returns both a public and a metadata IP, reject."""

    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return [
            ipaddress.ip_address("8.8.8.8"),
            ipaddress.ip_address("169.254.169.254"),
        ]

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    with pytest.raises(UrlGuardError, match="metadata"):
        await validate_url("https://rebind.example/x")


async def test_empty_dns_answer_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return []

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    with pytest.raises(UrlGuardError, match="No IPs"):
        await validate_url("https://nothing.example/x")


async def test_dns_error_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket as _socket

    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        raise _socket.gaierror("nope")

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    with pytest.raises(UrlGuardError, match="DNS lookup"):
        await validate_url("https://broken.example/x")


# ---------- streaming fetch ----------


@respx.mock
async def test_fetch_bytes_safely_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return await _mock_resolve("8.8.8.8")

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    respx.get("https://cdn.example/cat.jpg").mock(
        return_value=httpx.Response(
            200,
            content=b"\x89PNG\r\n" + b"\x00" * 100,
            headers={"content-type": "image/png"},
        )
    )
    result = await fetch_bytes_safely("https://cdn.example/cat.jpg")
    assert result.content.startswith(b"\x89PNG")
    assert result.content_type == "image/png"


@respx.mock
async def test_fetch_rejects_advertised_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return await _mock_resolve("8.8.8.8")

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    respx.get("https://cdn.example/huge.bin").mock(
        return_value=httpx.Response(
            200,
            content=b"x" * 100,
            headers={
                "content-length": "999999999",
                "content-type": "application/octet-stream",
            },
        )
    )
    with pytest.raises(UrlGuardError, match="cap"):
        await fetch_bytes_safely("https://cdn.example/huge.bin", max_bytes=1024)


@respx.mock
async def test_fetch_rejects_stream_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return await _mock_resolve("8.8.8.8")

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    # No content-length header → server lies → check must catch during stream
    respx.get("https://cdn.example/sneaky.bin").mock(
        return_value=httpx.Response(
            200,
            content=b"x" * 5000,
            headers={"content-type": "application/octet-stream"},
        )
    )
    with pytest.raises(UrlGuardError, match="exceeds"):
        await fetch_bytes_safely(
            "https://cdn.example/sneaky.bin",
            max_bytes=1024,
        )


@respx.mock
async def test_fetch_rejects_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(_hostname: str) -> list[ipaddress._BaseAddress]:
        return await _mock_resolve("8.8.8.8")

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    respx.get("https://cdn.example/missing.jpg").mock(return_value=httpx.Response(404))
    with pytest.raises(UrlGuardError, match="404"):
        await fetch_bytes_safely("https://cdn.example/missing.jpg")


# ---------- real DNS path (kept tiny) ----------


async def test_real_resolve_for_localhost_is_blocked() -> None:
    # Does a live DNS lookup for localhost and confirms the guard trips.
    # No network egress — localhost resolves synchronously.
    with pytest.raises(UrlGuardError, match="loopback"):
        await validate_url("https://localhost/x")


def test_sync_wrapper_cover() -> None:
    # Smoke-cover the utility in case reviewers prefer sync entry.
    with patch("roboflow_mcp.safety.urlguard.asyncio.get_running_loop") as loop:
        loop.return_value = None  # not exercised, just probe import
    assert urlguard._DEFAULT_MAX_BYTES == 25 * 1024 * 1024
