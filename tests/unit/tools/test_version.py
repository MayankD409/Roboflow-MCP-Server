"""Tests for roboflow_mcp.tools.version."""

from __future__ import annotations

import httpx
import pytest
import respx

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.config import ServerMode
from roboflow_mcp.errors import ConfigurationError, ToolDisabledError
from roboflow_mcp.models.upload import DeleteResult
from roboflow_mcp.models.version import (
    ExportResult,
    VersionDetail,
    VersionGenerationStatus,
)
from roboflow_mcp.tools import version as version_tools
from tests.conftest import SettingsFactory

# ---------- list ----------


@respx.mock
async def test_list_versions_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro/boxes").mock(
        return_value=httpx.Response(
            200,
            json={
                "versions": [
                    {
                        "id": "v1",
                        "name": "first",
                        "images": 100,
                        "model": {"arch": "yolov8"},
                    },
                    {"id": "v2", "name": "second", "images": 150},
                ]
            },
        )
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        versions = await version_tools.list_versions_impl(
            "boxes",
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(versions, list)
    assert len(versions) == 2
    assert versions[0].id == "v1"
    assert versions[0].trained is True
    assert versions[1].trained is False


# ---------- get ----------


@respx.mock
async def test_get_version_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro/boxes/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": {
                    "id": "1",
                    "name": "v1",
                    "images": 500,
                    "splits": {"train": 400, "valid": 50, "test": 50},
                    "classes": {"box": 500},
                    "trained": True,
                }
            },
        )
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        detail = await version_tools.get_version_impl(
            "boxes",
            "1",
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(detail, VersionDetail)
    assert detail.id == "1"
    assert detail.splits == {"train": 400, "valid": 50, "test": 50}


# ---------- create ----------


async def test_create_version_requires_confirm(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="confirm"):
            await version_tools.create_version_impl(
                "boxes",
                workspace=None,
                client=client,
                settings=settings,
            )


async def test_create_version_refuses_readonly(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro", mode=ServerMode.READONLY)
    async with RoboflowClient(settings) as client:
        with pytest.raises(ToolDisabledError, match="readonly"):
            await version_tools.create_version_impl(
                "boxes",
                workspace=None,
                confirm="yes",
                client=client,
                settings=settings,
            )


@respx.mock
async def test_create_version_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.post("https://api.roboflow.com/contoro/boxes/generate").mock(
        return_value=httpx.Response(200, json={"version": "2", "generating": True})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await version_tools.create_version_impl(
            "boxes",
            workspace=None,
            preprocessing={"resize": 640},
            augmentation={"rotate": 15},
            confirm="yes",
            client=client,
            settings=settings,
        )
    assert result["status"] == "generating"


# ---------- generation status ----------


@respx.mock
async def test_status_reports_generating(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro/boxes/2").mock(
        return_value=httpx.Response(200, json={"version": {"generating": True}})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        status = await version_tools.get_version_generation_status_impl(
            "boxes", "2", workspace=None, client=client, settings=settings
        )
    assert isinstance(status, VersionGenerationStatus)
    assert status.status == "generating"


@respx.mock
async def test_status_reports_ready(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro/boxes/2").mock(
        return_value=httpx.Response(200, json={"version": {"id": "2", "images": 500}})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        status = await version_tools.get_version_generation_status_impl(
            "boxes", "2", workspace=None, client=client, settings=settings
        )
    assert isinstance(status, VersionGenerationStatus)
    assert status.status == "ready"


@respx.mock
async def test_status_handles_404_as_generating(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro/boxes/2").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        status = await version_tools.get_version_generation_status_impl(
            "boxes", "2", workspace=None, client=client, settings=settings
        )
    assert isinstance(status, VersionGenerationStatus)
    assert status.status == "generating"


# ---------- export ----------


@respx.mock
async def test_export_version_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro/boxes/2/yolov8").mock(
        return_value=httpx.Response(
            200,
            json={"export": {"link": "https://download.example/abc.zip"}},
        )
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await version_tools.export_version_impl(
            "boxes",
            "2",
            "yolov8",
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(result, ExportResult)
    assert result.ready is True
    assert result.download_url == "https://download.example/abc.zip"


# ---------- delete ----------


async def test_delete_version_requires_confirm(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="confirm"):
            await version_tools.delete_version_impl(
                "boxes",
                "1",
                workspace=None,
                client=client,
                settings=settings,
            )


@respx.mock
async def test_delete_version_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.delete("https://api.roboflow.com/contoro/boxes/1").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await version_tools.delete_version_impl(
            "boxes",
            "1",
            workspace=None,
            confirm="yes",
            client=client,
            settings=settings,
        )
    assert isinstance(result, DeleteResult)
    assert result.success
    assert result.version == "1"
