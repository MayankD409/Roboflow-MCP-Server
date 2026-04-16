"""Tests for roboflow_mcp.guards."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from roboflow_mcp.config import RoboflowSettings, ServerMode
from roboflow_mcp.errors import ConfigurationError, ToolDisabledError
from roboflow_mcp.guards import (
    check_tool_allowed,
    check_workspace_allowed,
    destructive,
    is_tool_enabled,
    validate_bounds,
)


def _settings(**overrides: Any) -> RoboflowSettings:
    defaults: dict[str, Any] = dict(
        api_key=SecretStr("k"),
        workspace=None,
        api_url="https://api.roboflow.com",
        log_level="INFO",
        mode=ServerMode.CURATE,
        allow_tools=frozenset(),
        deny_tools=frozenset(),
        workspace_allowlist=frozenset(),
        allow_insecure=False,
        audit_log_path=None,
        rate_limit_per_minute=600,
        rate_limit_per_hour=10_000,
        circuit_breaker_threshold=100,
        circuit_breaker_cooldown_s=30.0,
        max_string_length=4096,
        max_list_length=1000,
    )
    defaults.update(overrides)
    return RoboflowSettings.model_construct(**defaults)


# ---- allow/deny list ----


def test_empty_lists_allow_all() -> None:
    check_tool_allowed("roboflow_search_images", allow=frozenset(), deny=frozenset())


def test_allow_list_blocks_unlisted_tools() -> None:
    with pytest.raises(ToolDisabledError, match="ALLOW_TOOLS"):
        check_tool_allowed(
            "roboflow_delete_image",
            allow=frozenset({"roboflow_get_workspace"}),
            deny=frozenset(),
        )


def test_deny_list_blocks_listed_tools() -> None:
    with pytest.raises(ToolDisabledError, match="DENY_TOOLS"):
        check_tool_allowed(
            "roboflow_delete_image",
            allow=frozenset(),
            deny=frozenset({"roboflow_delete_image"}),
        )


def test_deny_wins_over_allow() -> None:
    with pytest.raises(ToolDisabledError, match="DENY_TOOLS"):
        check_tool_allowed(
            "roboflow_delete_image",
            allow=frozenset({"roboflow_delete_image"}),
            deny=frozenset({"roboflow_delete_image"}),
        )


def test_is_tool_enabled_returns_false_for_denied() -> None:
    s = _settings(deny_tools=frozenset({"roboflow_delete_image"}))
    assert is_tool_enabled("roboflow_delete_image", s) is False
    assert is_tool_enabled("roboflow_get_workspace", s) is True


def test_is_tool_enabled_returns_false_when_not_in_allow_list() -> None:
    s = _settings(allow_tools=frozenset({"roboflow_get_workspace"}))
    assert is_tool_enabled("roboflow_get_workspace", s) is True
    assert is_tool_enabled("roboflow_search_images", s) is False


# ---- workspace allowlist ----


def test_empty_workspace_allowlist_permits_anything() -> None:
    check_workspace_allowed("contoro", frozenset())


def test_workspace_allowlist_rejects_unknown() -> None:
    with pytest.raises(ToolDisabledError, match="WORKSPACE_ALLOWLIST"):
        check_workspace_allowed("other", frozenset({"contoro"}))


def test_workspace_allowlist_accepts_listed() -> None:
    check_workspace_allowed("contoro", frozenset({"contoro", "acme"}))


# ---- destructive decorator ----


async def test_destructive_refuses_readonly_mode() -> None:
    @destructive
    async def _impl(*, confirm: str = "", settings: RoboflowSettings) -> str:
        return "did-a-thing"

    s = _settings(mode=ServerMode.READONLY)
    with pytest.raises(ToolDisabledError, match="readonly"):
        await _impl(confirm="yes", settings=s)


async def test_destructive_requires_confirm_token() -> None:
    @destructive
    async def _impl(*, confirm: str = "", settings: RoboflowSettings) -> str:
        return "ok"

    s = _settings(mode=ServerMode.CURATE)
    with pytest.raises(ConfigurationError, match="confirm"):
        await _impl(confirm="", settings=s)


async def test_destructive_runs_when_confirmed_and_curate() -> None:
    @destructive
    async def _impl(*, confirm: str = "", settings: RoboflowSettings) -> str:
        return "ok"

    s = _settings(mode=ServerMode.CURATE)
    result = await _impl(confirm="yes", settings=s)
    assert result == "ok"


async def test_destructive_runs_in_full_mode() -> None:
    @destructive
    async def _impl(*, confirm: str = "", settings: RoboflowSettings) -> str:
        return "ok"

    s = _settings(mode=ServerMode.FULL)
    result = await _impl(confirm="yes", settings=s)
    assert result == "ok"


async def test_destructive_requires_settings_kwarg() -> None:
    @destructive
    async def _impl(
        *, confirm: str = "", settings: RoboflowSettings | None = None
    ) -> str:
        return "ok"

    with pytest.raises(ConfigurationError, match="without settings"):
        await _impl(confirm="yes")


def test_destructive_flag_is_set_on_wrapper() -> None:
    @destructive
    async def _impl(**_: object) -> None:
        return None

    assert _impl._roboflow_mcp_destructive is True  # type: ignore[attr-defined]


# ---- validate_bounds ----


def test_validate_bounds_passes_for_reasonable_inputs() -> None:
    validate_bounds(
        {"tag": "sku-42", "tags": ["a", "b", "c"]},
        max_string=100,
        max_list=100,
    )


def test_validate_bounds_rejects_long_strings() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        validate_bounds(
            {"tag": "x" * 101},
            max_string=100,
            max_list=100,
        )


def test_validate_bounds_rejects_long_lists() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        validate_bounds(
            {"tags": ["x"] * 101},
            max_string=100,
            max_list=100,
        )


def test_validate_bounds_ignores_none_and_non_str() -> None:
    validate_bounds(
        {"tag": None, "limit": 100, "offset": 0},
        max_string=10,
        max_list=10,
    )
