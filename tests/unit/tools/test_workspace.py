"""Tests for roboflow_mcp.tools.workspace."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.errors import ConfigurationError
from roboflow_mcp.models.workspace import Project, Workspace
from roboflow_mcp.tools import workspace as workspace_tools
from tests.conftest import SettingsFactory

_WORKSPACE_PAYLOAD: dict[str, Any] = {
    "workspace": {
        "name": "Contoro Robotics",
        "url": "contoro",
        "members": 5,
        "projects": [
            {
                "id": "contoro/box-seg",
                "type": "instance-segmentation",
                "name": "Box Segmentation",
                "created": 1732000000,
                "updated": 1734000000,
                "images": 1200,
                "unannotated": 300,
                "annotation": "box",
                "versions": 4,
                "public": False,
                "splits": {"train": 800, "test": 200, "valid": 200},
                "classes": {"box": 1200, "wall": 600},
            },
            {
                "id": "contoro/lidar-detect",
                "type": "object-detection",
                "name": "Lidar Detection",
                "created": 1735000000,
                "updated": 1735500000,
                "images": 400,
                "unannotated": 10,
                "annotation": "obstacle",
                "versions": 2,
                "public": False,
                "splits": {"train": 320, "test": 40, "valid": 40},
                "classes": {"wall": 400, "pallet": 250},
            },
        ],
    }
}


@respx.mock
async def test_get_workspace_parses_full_payload(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro").mock(
        return_value=httpx.Response(200, json=_WORKSPACE_PAYLOAD)
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        ws = await workspace_tools.get_workspace_impl(
            None, client=client, settings=settings
        )

    assert isinstance(ws, Workspace)
    assert ws.name == "Contoro Robotics"
    assert ws.url == "contoro"
    assert ws.members == 5
    assert len(ws.projects) == 2
    first = ws.projects[0]
    assert first.id == "contoro/box-seg"
    assert first.type == "instance-segmentation"
    assert first.images == 1200
    assert first.classes == {"box": 1200, "wall": 600}


@respx.mock
async def test_get_workspace_uses_explicit_slug_over_default(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.get("https://api.roboflow.com/other").mock(
        return_value=httpx.Response(200, json=_WORKSPACE_PAYLOAD)
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        await workspace_tools.get_workspace_impl(
            "other", client=client, settings=settings
        )

    assert route.called


async def test_get_workspace_raises_when_no_slug(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace=None)
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="No workspace"):
            await workspace_tools.get_workspace_impl(
                None, client=client, settings=settings
            )


@respx.mock
async def test_list_projects_returns_all_projects(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro").mock(
        return_value=httpx.Response(200, json=_WORKSPACE_PAYLOAD)
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        projects = await workspace_tools.list_projects_impl(
            None, client=client, settings=settings
        )

    assert isinstance(projects, list)
    assert len(projects) == 2
    assert all(isinstance(p, Project) for p in projects)
    assert [p.id for p in projects] == ["contoro/box-seg", "contoro/lidar-detect"]


@respx.mock
async def test_list_projects_handles_empty_workspace(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro").mock(
        return_value=httpx.Response(
            200, json={"workspace": {"name": "Empty", "url": "contoro", "projects": []}}
        )
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        projects = await workspace_tools.list_projects_impl(
            None, client=client, settings=settings
        )

    assert projects == []


@respx.mock
async def test_tools_are_registered_on_server(
    settings_factory: SettingsFactory,
) -> None:
    from roboflow_mcp.server import build_server

    settings = settings_factory(workspace="contoro")
    mcp = build_server(settings)
    tools = await mcp.list_tools()
    names = {t.name for t in tools}

    assert "roboflow_get_workspace" in names
    assert "roboflow_list_projects" in names
