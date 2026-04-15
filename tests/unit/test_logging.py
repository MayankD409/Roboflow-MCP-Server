"""Tests for roboflow_mcp.logging."""

from __future__ import annotations

import logging

from roboflow_mcp.logging import (
    SecretScrubbingFormatter,
    configure_logging,
    scrub_secret,
)


def test_scrub_secret_replaces_literal() -> None:
    assert scrub_secret("key=abc123 is mine", "abc123") == "key=*** is mine"


def test_scrub_secret_catches_api_key_query_param() -> None:
    url = "https://api.roboflow.com/foo?api_key=leaked_value_here&split=train"
    cleaned = scrub_secret(url, "")
    assert "leaked_value_here" not in cleaned
    assert "api_key=***" in cleaned


def test_scrub_secret_is_noop_when_secret_empty_and_no_api_key() -> None:
    assert scrub_secret("nothing to hide", "") == "nothing to hide"


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
