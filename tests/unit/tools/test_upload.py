"""Tests for roboflow_mcp.tools.upload."""

from __future__ import annotations

import base64
import io
import ipaddress
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from PIL import Image

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.errors import (
    ConfigurationError,
    ImageGuardError,
    PathGuardError,
    ToolDisabledError,
    UrlGuardError,
)
from roboflow_mcp.models.upload import (
    BatchUploadResult,
    DeleteResult,
    ImageDetail,
    UploadResult,
)
from roboflow_mcp.safety import urlguard
from roboflow_mcp.tools import upload as upload_tools
from tests.conftest import SettingsFactory


def _png_bytes(w: int = 8, h: int = 8) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "red").save(buf, format="PNG")
    return buf.getvalue()


def _png_b64() -> str:
    return base64.b64encode(_png_bytes()).decode()


async def _public_ip_resolver(_hostname: str) -> list[ipaddress._BaseAddress]:
    return [ipaddress.ip_address("8.8.8.8")]


# ---------- upload_image ----------


@respx.mock
async def test_upload_image_base64_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.post("https://api.roboflow.com/dataset/boxes/upload").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "img_xyz"})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await upload_tools.upload_image_impl(
            "boxes",
            {"kind": "base64", "data": _png_b64(), "filename": "x.png"},
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(result, UploadResult)
    assert result.success is True
    assert result.filename == "x.png"
    assert result.raw["id"] == "img_xyz"


@respx.mock
async def test_upload_image_url(
    settings_factory: SettingsFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(urlguard, "_resolve_host", _public_ip_resolver)
    respx.get("https://cdn.example/cat.png").mock(
        return_value=httpx.Response(
            200, content=_png_bytes(), headers={"content-type": "image/png"}
        )
    )
    respx.post("https://api.roboflow.com/dataset/boxes/upload").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "img_cat"})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await upload_tools.upload_image_impl(
            "boxes",
            {"kind": "url", "url": "https://cdn.example/cat.png"},
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(result, UploadResult)
    assert result.success


async def test_upload_image_rejects_ssrf_url(
    settings_factory: SettingsFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake(_h: str) -> list[ipaddress._BaseAddress]:
        return [ipaddress.ip_address("169.254.169.254")]

    monkeypatch.setattr(urlguard, "_resolve_host", fake)
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(UrlGuardError, match="metadata"):
            await upload_tools.upload_image_impl(
                "boxes",
                {"kind": "url", "url": "https://attacker.com/x.png"},
                workspace=None,
                client=client,
                settings=settings,
            )


async def test_upload_image_rejects_http(
    settings_factory: SettingsFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(urlguard, "_resolve_host", _public_ip_resolver)
    settings = settings_factory(workspace="contoro", allow_insecure=False)
    async with RoboflowClient(settings) as client:
        with pytest.raises(UrlGuardError, match="scheme"):
            await upload_tools.upload_image_impl(
                "boxes",
                {"kind": "url", "url": "http://cdn.example/x.png"},
                workspace=None,
                client=client,
                settings=settings,
            )


async def test_upload_image_rejects_corrupt_base64(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ImageGuardError):
            await upload_tools.upload_image_impl(
                "boxes",
                {
                    "kind": "base64",
                    "data": base64.b64encode(b"not an image at all").decode(),
                    "filename": "fake.png",
                },
                workspace=None,
                client=client,
                settings=settings,
            )


async def test_upload_image_path_requires_roots(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    img = tmp_path / "x.png"
    img.write_bytes(_png_bytes())
    settings = settings_factory(workspace="contoro", upload_roots=())
    async with RoboflowClient(settings) as client:
        with pytest.raises(ImageGuardError, match="disabled"):
            await upload_tools.upload_image_impl(
                "boxes",
                {"kind": "path", "path": str(img)},
                workspace=None,
                client=client,
                settings=settings,
            )


@respx.mock
async def test_upload_image_path_happy(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    img = root / "cat.png"
    img.write_bytes(_png_bytes())
    respx.post("https://api.roboflow.com/dataset/boxes/upload").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "img_cat"})
    )
    settings = settings_factory(workspace="contoro", upload_roots=(root,))
    async with RoboflowClient(settings) as client:
        result = await upload_tools.upload_image_impl(
            "boxes",
            {"kind": "path", "path": str(img)},
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(result, UploadResult)
    assert result.filename == "cat.png"
    assert result.success


async def test_upload_image_path_traversal_rejected(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png_bytes())
    settings = settings_factory(workspace="contoro", upload_roots=(root,))
    async with RoboflowClient(settings) as client:
        with pytest.raises(PathGuardError, match="not under"):
            await upload_tools.upload_image_impl(
                "boxes",
                {"kind": "path", "path": str(outside)},
                workspace=None,
                client=client,
                settings=settings,
            )


async def test_upload_image_dry_run(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        preview = await upload_tools.upload_image_impl(
            "boxes",
            {"kind": "base64", "data": _png_b64(), "filename": "x.png"},
            workspace=None,
            dry_run=True,
            client=client,
            settings=settings,
        )
    assert isinstance(preview, dict)
    assert preview["dry_run"] is True
    assert preview["method"] == "POST"
    assert preview["path"] == "/dataset/boxes/upload"
    # api_key must be redacted
    assert preview["params"].get("api_key") == "***"


# ---------- batch upload ----------


@respx.mock
async def test_upload_images_batch_partial_failure(
    settings_factory: SettingsFactory,
) -> None:
    respx.post("https://api.roboflow.com/dataset/boxes/upload").mock(
        side_effect=[
            httpx.Response(200, json={"success": True, "id": "ok1"}),
            httpx.Response(500, json={"message": "boom"}),
            httpx.Response(200, json={"success": True, "id": "ok2"}),
        ]
    )
    settings = settings_factory(
        workspace="contoro",
        circuit_breaker_threshold=100,
    )
    sources: list[dict[str, Any]] = [
        {"kind": "base64", "data": _png_b64(), "filename": f"x{i}.png"}
        for i in range(3)
    ]
    async with RoboflowClient(settings) as client:
        result = await upload_tools.upload_images_batch_impl(
            "boxes",
            sources,
            workspace=None,
            concurrency=1,  # deterministic ordering
            client=client,
            settings=settings,
        )
    assert isinstance(result, BatchUploadResult)
    assert result.total == 3
    assert result.succeeded == 2
    assert result.failed == 1


async def test_upload_images_batch_rejects_empty(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ValueError, match="non-empty"):
            await upload_tools.upload_images_batch_impl(
                "boxes",
                [],
                workspace=None,
                client=client,
                settings=settings,
            )


async def test_upload_images_batch_rejects_bad_concurrency(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ValueError, match="concurrency"):
            await upload_tools.upload_images_batch_impl(
                "boxes",
                [{"kind": "base64", "data": _png_b64(), "filename": "x.png"}],
                workspace=None,
                concurrency=0,
                client=client,
                settings=settings,
            )


# ---------- delete_image ----------


@respx.mock
async def test_delete_image_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.delete("https://api.roboflow.com/contoro/boxes/images/img_abc").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await upload_tools.delete_image_impl(
            "boxes",
            "img_abc",
            workspace=None,
            confirm="yes",
            client=client,
            settings=settings,
        )
    assert isinstance(result, DeleteResult)
    assert result.success is True
    assert result.image_id == "img_abc"


async def test_delete_image_requires_confirm(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="confirm"):
            await upload_tools.delete_image_impl(
                "boxes",
                "img_abc",
                workspace=None,
                client=client,
                settings=settings,
            )


async def test_delete_image_refuses_readonly(
    settings_factory: SettingsFactory,
) -> None:
    from roboflow_mcp.config import ServerMode

    settings = settings_factory(workspace="contoro", mode=ServerMode.READONLY)
    async with RoboflowClient(settings) as client:
        with pytest.raises(ToolDisabledError, match="readonly"):
            await upload_tools.delete_image_impl(
                "boxes",
                "img_abc",
                workspace=None,
                confirm="yes",
                client=client,
                settings=settings,
            )


# ---------- get + list ----------


@respx.mock
async def test_get_image_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro/boxes/images/img_abc").mock(
        return_value=httpx.Response(
            200,
            json={
                "image": {
                    "name": "sample.jpg",
                    "tags": ["sku-42"],
                    "split": "train",
                }
            },
        )
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        detail = await upload_tools.get_image_impl(
            "boxes",
            "img_abc",
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(detail, ImageDetail)
    assert detail.id == "img_abc"
    assert detail.tags == ["sku-42"]
    assert detail.split == "train"


@respx.mock
async def test_list_image_batches_happy(
    settings_factory: SettingsFactory,
) -> None:
    respx.get("https://api.roboflow.com/contoro/boxes/batches").mock(
        return_value=httpx.Response(
            200,
            json={
                "batches": [
                    {"name": "2026-04-15", "image_count": 120},
                    {"name": "2026-04-14", "image_count": 90},
                ]
            },
        )
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        batches = await upload_tools.list_image_batches_impl(
            "boxes",
            workspace=None,
            client=client,
            settings=settings,
        )
    assert isinstance(batches, list)
    assert len(batches) == 2
    assert batches[0].name == "2026-04-15"
