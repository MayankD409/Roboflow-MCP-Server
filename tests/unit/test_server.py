"""Tests for roboflow_mcp.server skeleton."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import SecretStr

from roboflow_mcp.config import RoboflowSettings, ServerMode
from roboflow_mcp.server import build_server, main


def _make_settings(**overrides: Any) -> RoboflowSettings:
    defaults: dict[str, Any] = dict(
        api_key=SecretStr("k_test"),
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


def test_build_server_returns_fastmcp_instance() -> None:
    mcp = build_server(_make_settings())
    assert isinstance(mcp, FastMCP)


def test_build_server_has_expected_name() -> None:
    mcp = build_server(_make_settings())
    assert mcp.name == "mcp-server-roboflow"


async def test_list_tools_returns_all_tools() -> None:
    mcp = build_server(_make_settings())
    names = {tool.name for tool in await mcp.list_tools()}
    expected = {
        # v0.1
        "roboflow_get_workspace",
        "roboflow_list_projects",
        "roboflow_search_images",
        "roboflow_add_image_tags",
        "roboflow_remove_image_tags",
        "roboflow_set_image_tags",
        # v0.3 ingestion
        "roboflow_upload_image",
        "roboflow_upload_images_batch",
        "roboflow_delete_image",
        "roboflow_upload_annotation",
        "roboflow_get_image",
        "roboflow_list_image_batches",
        "roboflow_get_project",
        "roboflow_list_versions",
        "roboflow_get_version",
        "roboflow_create_version",
        "roboflow_get_version_generation_status",
        "roboflow_export_version",
        "roboflow_delete_version",
        "roboflow_download_export",
    }
    assert expected <= names, f"Missing tools: {expected - names}"


async def test_v03_resource_registered() -> None:
    mcp = build_server(_make_settings())
    resources = await mcp.list_resource_templates()
    uris = {str(r.uriTemplate) for r in resources}
    assert any("roboflow://workspace/" in uri and "versions" in uri for uri in uris), (
        f"version resource not registered (got {uris})"
    )


async def test_allow_list_filters_registration() -> None:
    settings = _make_settings(
        allow_tools=frozenset({"roboflow_get_workspace", "roboflow_list_projects"})
    )
    mcp = build_server(settings)
    names = {tool.name for tool in await mcp.list_tools()}
    assert names == {"roboflow_get_workspace", "roboflow_list_projects"}


async def test_deny_list_filters_registration() -> None:
    settings = _make_settings(
        deny_tools=frozenset({"roboflow_remove_image_tags", "roboflow_set_image_tags"})
    )
    mcp = build_server(settings)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "roboflow_remove_image_tags" not in names
    assert "roboflow_set_image_tags" not in names
    assert "roboflow_add_image_tags" in names


def test_main_invokes_run_over_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k_test")

    with patch("roboflow_mcp.server.FastMCP.run") as run_mock:
        main()

    run_mock.assert_called_once()
    assert run_mock.call_args.kwargs.get("transport") == "stdio"
