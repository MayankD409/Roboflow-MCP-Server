"""Tests for roboflow_mcp.tools.project."""

from __future__ import annotations

import httpx
import respx

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.models.version import ProjectDetail
from roboflow_mcp.tools import project as project_tools
from tests.conftest import SettingsFactory


@respx.mock
async def test_get_project_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro/boxes").mock(
        return_value=httpx.Response(
            200,
            json={
                "project": {
                    "id": "contoro/boxes",
                    "type": "object-detection",
                    "name": "Boxes",
                    "images": 500,
                    "classes": {"box": 500},
                }
            },
        )
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        detail = await project_tools.get_project_impl(
            "boxes",
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(detail, ProjectDetail)
    assert detail.id == "contoro/boxes"
    assert detail.type == "object-detection"
    assert detail.classes == {"box": 500}


async def test_get_project_dry_run(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        preview = await project_tools.get_project_impl(
            "boxes",
            workspace=None,
            dry_run=True,
            client=client,
            settings=settings,
        )
    assert isinstance(preview, dict)
    assert preview["dry_run"] is True
    assert preview["path"] == "/contoro/boxes"
