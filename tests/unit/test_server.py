"""Tests for roboflow_mcp.server skeleton."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import SecretStr

from roboflow_mcp.config import RoboflowSettings
from roboflow_mcp.server import build_server, main


def _make_settings() -> RoboflowSettings:
    return RoboflowSettings.model_construct(
        api_key=SecretStr("k_test"),
        workspace=None,
        api_url="https://api.roboflow.com",
        log_level="INFO",
    )


def test_build_server_returns_fastmcp_instance() -> None:
    mcp = build_server(_make_settings())
    assert isinstance(mcp, FastMCP)


def test_build_server_has_expected_name() -> None:
    mcp = build_server(_make_settings())
    assert mcp.name == "mcp-server-roboflow"


async def test_list_tools_starts_empty() -> None:
    mcp = build_server(_make_settings())
    tools = await mcp.list_tools()
    assert tools == []


def test_main_invokes_run_over_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k_test")

    with patch("roboflow_mcp.server.FastMCP.run") as run_mock:
        main()

    run_mock.assert_called_once()
    assert run_mock.call_args.kwargs.get("transport") == "stdio"
