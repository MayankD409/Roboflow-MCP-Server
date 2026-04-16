"""Red-team: every documented SSRF exfil target must be rejected by urlguard.

If any of these pass, someone has broken the defender. Run with:

    uv run pytest tests/redteam/ -v -m redteam
"""

from __future__ import annotations

import ipaddress

import pytest

from roboflow_mcp.errors import UrlGuardError
from roboflow_mcp.safety import urlguard
from roboflow_mcp.safety.urlguard import validate_url

pytestmark = pytest.mark.redteam


# Known SSRF exfil targets. Each is a (hostname, resolved_ip, why_bad)
# triple. Hostname is fake — the resolver is mocked.
_EXFIL_TARGETS = [
    # AWS IMDS v1 + v2
    ("metadata-attacker.example", "169.254.169.254", "AWS IMDS"),
    # GCP metadata
    ("metadata.google.internal.attacker.example", "169.254.169.254", "GCP metadata"),
    # Azure IMDS
    ("169.254.169.254.azure.attacker", "169.254.169.254", "Azure IMDS"),
    # ECS task metadata
    ("ecs-metadata.attacker.example", "169.254.170.2", "ECS task metadata"),
    # AWS IMDSv2 IPv6
    ("aws-v6.attacker.example", "fd00:ec2::254", "AWS IMDSv2 IPv6"),
    # Localhost escape attempts
    ("localhost-attacker.example", "127.0.0.1", "localhost"),
    ("loopback-alias.example", "127.1.2.3", "loopback"),
    ("v6-loopback.example", "::1", "IPv6 loopback"),
    # Kubernetes + Docker internals
    ("kubernetes-attacker.example", "10.0.0.1", "RFC1918 / K8s"),
    ("docker-attacker.example", "172.17.0.2", "RFC1918 / Docker"),
    ("192-168-attacker.example", "192.168.1.100", "RFC1918"),
    # Link-local
    ("link-local-ipv6.example", "fe80::1", "link-local IPv6"),
    # Unspecified / reserved
    ("zero-attacker.example", "0.0.0.0", "unspecified"),
    ("v6-zero.example", "::", "unspecified IPv6"),
]


@pytest.mark.parametrize(
    "hostname,ip,reason", _EXFIL_TARGETS, ids=[t[2] for t in _EXFIL_TARGETS]
)
async def test_exfil_target_rejected(
    hostname: str, ip: str, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake(_h: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        return [ipaddress.ip_address(ip)]

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    with pytest.raises(UrlGuardError):
        await validate_url(f"https://{hostname}/exfil")


# Scheme-level attackers that shouldn't even reach DNS resolution.
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "file:///c:/windows/system32/drivers/etc/hosts",
        "ftp://attacker.example/etc/passwd",
        "gopher://attacker.example/_GET%20/",
        "dict://attacker.example:11211/",
        "ldap://attacker.example/dc=example",
        "jar:http://attacker.example/x.jar!/a",
        "netdoc://attacker.example/",
        # SMB
        "smb://attacker.example/secrets",
        # javascript: (blocked by urllib parse)
        "javascript:alert(1)",
    ],
)
async def test_scheme_attacks_rejected(url: str) -> None:
    with pytest.raises(UrlGuardError):
        await validate_url(url)


# Credential-bearing URLs (often accidental leaks)
async def test_basic_auth_url_rejected() -> None:
    with pytest.raises(UrlGuardError, match="credentials"):
        await validate_url("https://user:hunter2@example.com/x")


# Missing-hostname attacks (blob: or malformed)
@pytest.mark.parametrize(
    "url",
    [
        "https:///no-host",
        "https://",
    ],
)
async def test_malformed_hostname_rejected(url: str) -> None:
    with pytest.raises(UrlGuardError):
        await validate_url(url)
