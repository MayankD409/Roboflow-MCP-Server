"""Tests for roboflow_mcp.tools.image."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.errors import ConfigurationError
from roboflow_mcp.models.image import ImageSearchResult, ImageSummary
from roboflow_mcp.tools import image as image_tools
from tests.conftest import SettingsFactory

# ---------- model parsing regressions ----------


def test_image_summary_accepts_int_created_unix_ms() -> None:
    # Regression: Roboflow's docs claim `created` is a string but the live API
    # returns it as an int (Unix milliseconds, e.g. 1715286185986). Caught
    # against a real workspace during v0.1 verification.
    img = ImageSummary.model_validate(
        {"id": "abc", "name": "x.jpg", "tags": [], "created": 1715286185986}
    )
    assert img.created == 1715286185986


def test_image_summary_still_accepts_string_created() -> None:
    img = ImageSummary.model_validate(
        {"id": "abc", "name": "x.jpg", "tags": [], "created": "2026-04-15T12:00:00Z"}
    )
    assert img.created == "2026-04-15T12:00:00Z"


def test_image_summary_accepts_missing_created() -> None:
    img = ImageSummary.model_validate({"id": "abc", "name": "x.jpg"})
    assert img.created is None


_SEARCH_PAYLOAD: dict[str, Any] = {
    "offset": 0,
    "total": 2,
    "results": [
        {
            "id": "img_abc",
            "name": "container_001.jpg",
            "owner": "mayank",
            "annotations": {"count": 3, "classes": {"box": 3}},
            "labels": [],
            "tags": ["sku-42", "2026-04"],
            "created": "2026-04-10T12:00:00Z",
            "split": "train",
        },
        {
            "id": "img_def",
            "name": "container_002.jpg",
            "tags": ["sku-42"],
            "split": "valid",
        },
    ],
}


def _body(request: httpx.Request) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(request.content)
    return parsed


# ---------- search_images ----------


@respx.mock
async def test_search_images_sends_tag_filter(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.post("https://api.roboflow.com/contoro/boxes/search").mock(
        return_value=httpx.Response(200, json=_SEARCH_PAYLOAD)
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await image_tools.search_images_impl(
            project="boxes",
            workspace=None,
            tag="sku-42",
            client=client,
            settings=settings,
        )

    assert route.called
    body = _body(route.calls.last.request)
    assert body["tag"] == "sku-42"
    assert isinstance(result, ImageSearchResult)
    assert result.total == 2
    assert isinstance(result.results[0], ImageSummary)
    assert result.results[0].tags == ["sku-42", "2026-04"]


@respx.mock
async def test_search_images_clamps_limit_to_max(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.post("https://api.roboflow.com/contoro/boxes/search").mock(
        return_value=httpx.Response(200, json=_SEARCH_PAYLOAD)
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        await image_tools.search_images_impl(
            project="boxes",
            workspace=None,
            limit=9999,
            client=client,
            settings=settings,
        )

    assert _body(route.calls.last.request)["limit"] == 250


@respx.mock
async def test_search_images_uses_default_fields(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.post("https://api.roboflow.com/contoro/boxes/search").mock(
        return_value=httpx.Response(200, json=_SEARCH_PAYLOAD)
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        await image_tools.search_images_impl(
            project="boxes",
            workspace=None,
            client=client,
            settings=settings,
        )

    fields = _body(route.calls.last.request)["fields"]
    assert "id" in fields
    assert "tags" in fields


@respx.mock
async def test_search_images_honours_explicit_workspace(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.post("https://api.roboflow.com/other/boxes/search").mock(
        return_value=httpx.Response(200, json=_SEARCH_PAYLOAD)
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        await image_tools.search_images_impl(
            project="boxes",
            workspace="other",
            client=client,
            settings=settings,
        )

    assert route.called


async def test_search_images_requires_workspace(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace=None)
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError):
            await image_tools.search_images_impl(
                project="boxes",
                workspace=None,
                client=client,
                settings=settings,
            )


# ---------- tag operations ----------


@respx.mock
async def test_add_tags_posts_add_operation(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.post(
        "https://api.roboflow.com/contoro/boxes/images/img_abc/tags"
    ).mock(return_value=httpx.Response(200, json={"ok": True}))
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await image_tools.add_image_tags_impl(
            project="boxes",
            image_id="img_abc",
            tags=["sku-42"],
            workspace=None,
            client=client,
            settings=settings,
        )

    body = _body(route.calls.last.request)
    assert body == {"operation": "add", "tags": ["sku-42"]}
    assert result["operation"] == "add"
    assert result["tags"] == ["sku-42"]
    assert result["image_id"] == "img_abc"


@respx.mock
async def test_remove_tags_posts_remove_operation(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.post(
        "https://api.roboflow.com/contoro/boxes/images/img_abc/tags"
    ).mock(return_value=httpx.Response(200, json={"ok": True}))
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        await image_tools.remove_image_tags_impl(
            project="boxes",
            image_id="img_abc",
            tags=["stale", "old"],
            workspace=None,
            confirm="yes",
            client=client,
            settings=settings,
        )

    body = _body(route.calls.last.request)
    assert body == {"operation": "remove", "tags": ["stale", "old"]}


@respx.mock
async def test_set_tags_posts_set_operation(
    settings_factory: SettingsFactory,
) -> None:
    route = respx.post(
        "https://api.roboflow.com/contoro/boxes/images/img_abc/tags"
    ).mock(return_value=httpx.Response(200, json={"ok": True}))
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        await image_tools.set_image_tags_impl(
            project="boxes",
            image_id="img_abc",
            tags=["sku-42", "2026-04"],
            workspace=None,
            confirm="yes",
            client=client,
            settings=settings,
        )

    body = _body(route.calls.last.request)
    assert body == {"operation": "set", "tags": ["sku-42", "2026-04"]}


async def test_remove_tags_requires_confirm(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="confirm"):
            await image_tools.remove_image_tags_impl(
                project="boxes",
                image_id="img_abc",
                tags=["stale"],
                workspace=None,
                # confirm missing -> default ""
                client=client,
                settings=settings,
            )


async def test_remove_tags_refuses_readonly_mode(
    settings_factory: SettingsFactory,
) -> None:
    from roboflow_mcp.config import ServerMode
    from roboflow_mcp.errors import ToolDisabledError

    settings = settings_factory(workspace="contoro", mode=ServerMode.READONLY)
    async with RoboflowClient(settings) as client:
        with pytest.raises(ToolDisabledError, match="readonly"):
            await image_tools.remove_image_tags_impl(
                project="boxes",
                image_id="img_abc",
                tags=["stale"],
                workspace=None,
                confirm="yes",
                client=client,
                settings=settings,
            )


async def test_search_dry_run_does_not_hit_api(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        preview = await image_tools.search_images_impl(
            project="boxes",
            workspace=None,
            tag="sku-42",
            dry_run=True,
            client=client,
            settings=settings,
        )

    assert isinstance(preview, dict)
    assert preview["dry_run"] is True
    assert preview["method"] == "POST"
    assert preview["path"].endswith("/boxes/search")


async def test_tag_ops_reject_empty_list(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ValueError, match="tags"):
            await image_tools.add_image_tags_impl(
                project="boxes",
                image_id="img_abc",
                tags=[],
                workspace=None,
                client=client,
                settings=settings,
            )


@respx.mock
async def test_image_tools_registered_on_server(
    settings_factory: SettingsFactory,
) -> None:
    from roboflow_mcp.server import build_server

    settings = settings_factory(workspace="contoro")
    mcp = build_server(settings)
    names = {t.name for t in await mcp.list_tools()}

    assert "roboflow_search_images" in names
    assert "roboflow_add_image_tags" in names
    assert "roboflow_remove_image_tags" in names
    assert "roboflow_set_image_tags" in names
