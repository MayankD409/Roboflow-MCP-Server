"""Tests for roboflow_mcp.errors."""

from __future__ import annotations

from roboflow_mcp.errors import (
    AuthenticationError,
    ConfigurationError,
    NotFoundError,
    RateLimitError,
    RoboflowAPIError,
    RoboflowMCPError,
)


def test_all_errors_inherit_from_base() -> None:
    for exc in (
        ConfigurationError,
        AuthenticationError,
        NotFoundError,
        RateLimitError,
        RoboflowAPIError,
    ):
        assert issubclass(exc, RoboflowMCPError)


def test_rate_limit_carries_retry_after() -> None:
    err = RateLimitError("slow down", retry_after=12.5)

    assert err.retry_after == 12.5
    assert "slow down" in str(err)


def test_rate_limit_defaults_retry_after_to_none() -> None:
    err = RateLimitError("slow down")

    assert err.retry_after is None


def test_api_error_carries_status_and_payload() -> None:
    err = RoboflowAPIError(500, "boom", payload={"details": "stack trace"})

    assert err.status == 500
    assert err.payload == {"details": "stack trace"}
    assert "500" in str(err)
    assert "boom" in str(err)


def test_api_error_default_payload_is_empty_dict() -> None:
    err = RoboflowAPIError(418, "teapot")

    assert err.payload == {}
