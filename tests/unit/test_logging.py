"""Tests for roboflow_mcp.logging — includes a 20+ leak-vector fixture.

Whenever the scrubber misses a pattern in production, add a new vector here.
This test file is the single source of truth for what "secrets never log"
means in practice.
"""

from __future__ import annotations

import logging

import pytest

from roboflow_mcp.logging import (
    SecretScrubbingFormatter,
    configure_logging,
    scrub_many,
    scrub_secret,
)

_SECRET = "rf_live_SUPER_SECRET_abcdef123456"


# --- 20+ leak vectors --------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_substring_not_present",
    [
        # Literal secret
        (f"key is {_SECRET} now", _SECRET),
        # api_key= in a URL
        (f"GET /workspace?api_key={_SECRET}&x=y", _SECRET),
        # api_key= with lowercase variation
        (f"https://api.roboflow.com/project?API_KEY={_SECRET}", _SECRET),
        # Authorization header
        (f"Authorization: Bearer {_SECRET}", _SECRET),
        # Authorization header without Bearer prefix
        (f"Authorization: {_SECRET}", _SECRET),
        # X-Api-Key header
        (f"X-Api-Key: {_SECRET}", _SECRET),
        # X-API-KEY in caps
        (f"X-API-KEY: {_SECRET}", _SECRET),
        # X-Auth-Token header
        (f"X-Auth-Token: {_SECRET}", _SECRET),
        # JSON body — api_key field
        (f'{{"api_key": "{_SECRET}", "other": "ok"}}', _SECRET),
        # JSON body — apiKey camelCase
        (f'{{"apiKey":"{_SECRET}"}}', _SECRET),
        # JSON body — authorization
        (f'{{"authorization": "{_SECRET}"}}', _SECRET),
        # Python repr of a dict
        (f"{{'api_key': '{_SECRET}', 'x': 1}}", _SECRET),
        # Nested dict repr
        (f"headers={{'x-api-key': '{_SECRET}'}}", _SECRET),
        # URL params order-insensitive (secret first)
        (f"?api_key={_SECRET}&tag=x", _SECRET),
        # URL params with secret mid-chain
        (f"?page=1&api_key={_SECRET}&limit=10", _SECRET),
        # Mixed casing for Authorization
        (f"authorization: bearer {_SECRET}", _SECRET),
        # Whitespace before header value
        (f"Authorization:    Bearer   {_SECRET}", _SECRET),
        # Trailing comma in JSON
        (f'{{"api_key":"{_SECRET}","tag":"x"}}', _SECRET),
        # Python f-string-like repr
        (f"authToken='{_SECRET}'", _SECRET),
        # auth_token snake_case in JSON
        (f'{{"auth_token":"{_SECRET}"}}', _SECRET),
        # Token scheme in Authorization
        (f"Authorization: Token {_SECRET}", _SECRET),
    ],
)
def test_scrubber_catches_leak_vector(
    raw: str, expected_substring_not_present: str
) -> None:
    cleaned = scrub_secret(raw, _SECRET)
    assert expected_substring_not_present not in cleaned, f"Leak: {cleaned!r}"


# --- original behaviours ----------------------------------------------------


def test_scrub_secret_replaces_literal() -> None:
    assert scrub_secret("key=abc123 is mine", "abc123") == "key=*** is mine"


def test_scrub_secret_catches_api_key_query_param_without_literal() -> None:
    url = "https://api.roboflow.com/foo?api_key=leaked_value_here&split=train"
    cleaned = scrub_secret(url, "")
    assert "leaked_value_here" not in cleaned
    assert "api_key=***" in cleaned


def test_scrub_secret_is_noop_when_secret_empty_and_no_api_key() -> None:
    assert scrub_secret("nothing to hide", "") == "nothing to hide"


def test_scrub_many_handles_multiple_secrets() -> None:
    text = "keyA=alpha keyB=beta"
    cleaned = scrub_many(text, ("alpha", "beta"))
    assert "alpha" not in cleaned
    assert "beta" not in cleaned


def test_formatter_scrubs_records() -> None:
    formatter = SecretScrubbingFormatter(fmt="%(message)s", secret="mykey")
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="calling with key=mykey now",
        args=None,
        exc_info=None,
    )

    out = formatter.format(record)

    assert "mykey" not in out
    assert "***" in out


def test_formatter_extra_secrets() -> None:
    formatter = SecretScrubbingFormatter(
        fmt="%(message)s", secret="primary", extra_secrets=("secondary",)
    )
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="primary and secondary",
        args=None,
        exc_info=None,
    )
    out = formatter.format(record)
    assert "primary" not in out
    assert "secondary" not in out


def test_configure_logging_sets_level_and_scrubs() -> None:
    configure_logging("WARNING", secret="topsecret")
    root = logging.getLogger()

    assert root.level == logging.WARNING

    handler = root.handlers[0]
    record = logging.LogRecord(
        name="x",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="leak topsecret",
        args=None,
        exc_info=None,
    )
    assert "topsecret" not in handler.format(record)
