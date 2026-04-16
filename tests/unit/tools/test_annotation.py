"""Tests for roboflow_mcp.tools.annotation."""

from __future__ import annotations

import httpx
import pytest
import respx

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.models.annotation import AnnotationResult
from roboflow_mcp.tools import annotation as annotation_tools
from tests.conftest import SettingsFactory


@respx.mock
async def test_upload_annotation_coco(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.post("https://api.roboflow.com/dataset/boxes/annotate/img_abc").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await annotation_tools.upload_annotation_impl(
            "boxes",
            "img_abc",
            {"images": [{"id": 1}], "annotations": []},
            "coco",
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(result, AnnotationResult)
    assert result.success is True
    assert result.format == "coco"
    # Roboflow routed the request with `name=coco`
    sent = dict(route.calls.last.request.url.params)
    assert sent["name"] == "coco"


@respx.mock
async def test_upload_annotation_yolo_maps_to_yolov8(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.post("https://api.roboflow.com/dataset/boxes/annotate/img_abc").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        await annotation_tools.upload_annotation_impl(
            "boxes",
            "img_abc",
            "0 0.5 0.5 0.2 0.2\n",
            "yolo",
            workspace=None,
            client=client,
            settings=settings,
        )
    sent = dict(route.calls.last.request.url.params)
    assert sent["name"] == "yolov8"


async def test_upload_annotation_rejects_bad_format(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ValueError, match="Unknown annotation_format"):
            await annotation_tools.upload_annotation_impl(
                "boxes",
                "img_abc",
                "x",
                "bogus",  # type: ignore[arg-type]
                workspace=None,
                client=client,
                settings=settings,
            )


async def test_upload_annotation_rejects_oversize(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    huge = "x" * (9 * 1024 * 1024)
    async with RoboflowClient(settings) as client:
        with pytest.raises(ValueError, match="exceeds"):
            await annotation_tools.upload_annotation_impl(
                "boxes",
                "img_abc",
                huge,
                "yolo",
                workspace=None,
                client=client,
                settings=settings,
            )


async def test_upload_annotation_dry_run(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        preview = await annotation_tools.upload_annotation_impl(
            "boxes",
            "img_abc",
            "0 0.5 0.5 0.2 0.2",
            "yolo",
            workspace=None,
            dry_run=True,
            client=client,
            settings=settings,
        )
    assert isinstance(preview, dict)
    assert preview["dry_run"] is True
    assert preview["params"].get("name") == "yolov8"
    assert preview["params"].get("api_key") == "***"
