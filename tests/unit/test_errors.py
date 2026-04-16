"""Tests for roboflow_mcp.errors."""

from __future__ import annotations

from roboflow_mcp.errors import (
    AuthenticationError,
    CircuitOpenError,
    ConfigurationError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    RoboflowAPIError,
    RoboflowMCPError,
    ToolDisabledError,
)


def test_all_errors_inherit_from_base() -> None:
    for exc in (
        ConfigurationError,
        AuthenticationError,
        NotFoundError,
        RateLimitError,
        RoboflowAPIError,
        QuotaExceededError,
        CircuitOpenError,
        ToolDisabledError,
    ):
        assert issubclass(exc, RoboflowMCPError)


def test_tool_disabled_is_configuration_error() -> None:
    # ToolDisabledError should be catchable as a ConfigurationError so existing
    # except-branches in host code keep working.
    assert issubclass(ToolDisabledError, ConfigurationError)


def test_quota_exceeded_carries_retry_after() -> None:
    err = QuotaExceededError("too many", retry_after=5.0)
    assert err.retry_after == 5.0


def test_circuit_open_carries_retry_after() -> None:
    err = CircuitOpenError("cooling", retry_after=12.0)
    assert err.retry_after == 12.0


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
