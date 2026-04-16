"""Tests for roboflow_mcp.tools.download."""

from __future__ import annotations

import io
import ipaddress
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.errors import ConfigurationError, UrlGuardError
from roboflow_mcp.models.version import DownloadResult
from roboflow_mcp.safety import urlguard
from roboflow_mcp.tools import download as download_tools
from tests.conftest import SettingsFactory


def _benign_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("train/image.jpg", b"\xff\xd8\xff\xe0")
        z.writestr("valid/image.jpg", b"\xff\xd8\xff\xe0")
        z.writestr("data.yaml", b"nc: 1\nnames: ['box']\n")
    return buf.getvalue()


def _zip_slip() -> bytes:
    """A zip whose entry resolves outside the extraction directory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../../etc/nope.txt", b"gotcha")
    return buf.getvalue()


def _zip_with_symlink() -> bytes:
    """A zip entry flagged as a Unix symlink."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = zipfile.ZipInfo(filename="link")
        info.external_attr = (0o120755 & 0xFFFF) << 16  # symlink mode
        z.writestr(info, "/etc/passwd")
    return buf.getvalue()


async def _public(
    _hostname: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("8.8.8.8")]


@respx.mock
async def test_download_export_with_direct_url(
    settings_factory: SettingsFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(urlguard, "_resolve_host", _public)
    zip_data = _benign_zip()
    respx.get("https://download.example/abc.zip").mock(
        return_value=httpx.Response(
            200,
            content=zip_data,
            headers={"content-type": "application/zip"},
        )
    )
    settings = settings_factory(
        workspace="contoro",
        export_cache_dir=tmp_path / "cache",
    )
    async with RoboflowClient(settings) as client:
        result = await download_tools.download_export_impl(
            "boxes",
            "2",
            "yolov8",
            workspace=None,
            download_url="https://download.example/abc.zip",
            extract=False,
            confirm="yes",
            client=client,
            settings=settings,
        )
    assert isinstance(result, DownloadResult)
    assert Path(result.path).exists()
    assert result.bytes == len(zip_data)
    assert not result.extracted


@respx.mock
async def test_download_export_extracts(
    settings_factory: SettingsFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(urlguard, "_resolve_host", _public)
    respx.get("https://download.example/abc.zip").mock(
        return_value=httpx.Response(200, content=_benign_zip())
    )
    settings = settings_factory(
        workspace="contoro",
        export_cache_dir=tmp_path / "cache",
    )
    async with RoboflowClient(settings) as client:
        result = await download_tools.download_export_impl(
            "boxes",
            "2",
            "yolov8",
            workspace=None,
            download_url="https://download.example/abc.zip",
            extract=True,
            confirm="yes",
            client=client,
            settings=settings,
        )
    assert isinstance(result, DownloadResult)
    assert result.extracted is True
    extracted_root = Path(result.path).parent / Path(result.path).stem
    assert (extracted_root / "train" / "image.jpg").exists()
    assert (extracted_root / "data.yaml").exists()


@respx.mock
async def test_download_export_refuses_zip_slip(
    settings_factory: SettingsFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(urlguard, "_resolve_host", _public)
    respx.get("https://download.example/slip.zip").mock(
        return_value=httpx.Response(200, content=_zip_slip())
    )
    settings = settings_factory(
        workspace="contoro",
        export_cache_dir=tmp_path / "cache",
    )
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match=r"traversing|zip-slip"):
            await download_tools.download_export_impl(
                "boxes",
                "2",
                "yolov8",
                workspace=None,
                download_url="https://download.example/slip.zip",
                extract=True,
                confirm="yes",
                client=client,
                settings=settings,
            )
    # Verify nothing escaped to the parent
    assert not (tmp_path.parent / "etc" / "nope.txt").exists()


@respx.mock
async def test_download_export_refuses_symlink_zip_entry(
    settings_factory: SettingsFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(urlguard, "_resolve_host", _public)
    respx.get("https://download.example/link.zip").mock(
        return_value=httpx.Response(200, content=_zip_with_symlink())
    )
    settings = settings_factory(
        workspace="contoro",
        export_cache_dir=tmp_path / "cache",
    )
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="symlink"):
            await download_tools.download_export_impl(
                "boxes",
                "2",
                "yolov8",
                workspace=None,
                download_url="https://download.example/link.zip",
                extract=True,
                confirm="yes",
                client=client,
                settings=settings,
            )


async def test_download_export_ssrf_rejected(
    settings_factory: SettingsFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An LLM-supplied download_url that resolves to a metadata IP must
    be rejected before any byte is fetched."""

    async def metadata(_h: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        return [ipaddress.ip_address("169.254.169.254")]

    monkeypatch.setattr(urlguard, "_resolve_host", metadata)
    settings = settings_factory(
        workspace="contoro",
        export_cache_dir=tmp_path / "cache",
    )
    async with RoboflowClient(settings) as client:
        with pytest.raises(UrlGuardError, match="metadata"):
            await download_tools.download_export_impl(
                "boxes",
                "2",
                "yolov8",
                workspace=None,
                download_url="https://attacker.example/exfil",
                confirm="yes",
                client=client,
                settings=settings,
            )


async def test_download_export_dest_dir_outside_cache_rejected(
    settings_factory: SettingsFactory,
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    evil = tmp_path / "evil"
    evil.mkdir()
    settings = settings_factory(
        workspace="contoro",
        export_cache_dir=cache,
    )
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="not under"):
            await download_tools.download_export_impl(
                "boxes",
                "2",
                "yolov8",
                workspace=None,
                download_url="https://ignored.example/x.zip",
                dest_dir=str(evil),
                confirm="yes",
                client=client,
                settings=settings,
            )


async def test_download_export_path_traversal_in_slug_sanitised(
    settings_factory: SettingsFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even a workspace slug like ``../../etc`` cannot escape the cache
    root — _sanitize_component strips the traversal characters."""
    monkeypatch.setattr(urlguard, "_resolve_host", _public)
    cache = tmp_path / "cache"
    settings = settings_factory(
        workspace="../../etc",
        workspace_allowlist=frozenset(),  # lifted so the crafted slug reaches the sanitiser
        export_cache_dir=cache,
    )

    @respx.mock
    async def go() -> None:
        respx.get("https://download.example/abc.zip").mock(
            return_value=httpx.Response(200, content=_benign_zip())
        )
        async with RoboflowClient(settings) as client:
            result = await download_tools.download_export_impl(
                "boxes",
                "2",
                "yolov8",
                workspace=None,
                download_url="https://download.example/abc.zip",
                confirm="yes",
                client=client,
                settings=settings,
            )
        assert isinstance(result, DownloadResult)
        zip_path = Path(result.path)
        # Must still be inside the cache — sanitiser turned ".." into "_".
        assert cache.resolve() in zip_path.resolve().parents

    await go()


async def test_download_export_disabled_raises(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    settings = settings_factory(
        workspace="contoro",
        export_cache_dir=tmp_path / "cache",
        enable_downloads=False,
    )
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="disabled"):
            await download_tools.download_export_impl(
                "boxes",
                "2",
                "yolov8",
                workspace=None,
                download_url="https://ignored",
                confirm="yes",
                client=client,
                settings=settings,
            )


async def test_download_export_requires_confirm(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    settings = settings_factory(
        workspace="contoro",
        export_cache_dir=tmp_path / "cache",
    )
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="confirm"):
            await download_tools.download_export_impl(
                "boxes",
                "2",
                "yolov8",
                workspace=None,
                download_url="https://download.example/abc.zip",
                client=client,
                settings=settings,
            )


async def test_download_export_dry_run(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    settings = settings_factory(
        workspace="contoro",
        export_cache_dir=tmp_path / "cache",
    )
    async with RoboflowClient(settings) as client:
        preview = await download_tools.download_export_impl(
            "boxes",
            "2",
            "yolov8",
            workspace=None,
            download_url="https://download.example/abc.zip",
            confirm="yes",
            dry_run=True,
            client=client,
            settings=settings,
        )
    assert isinstance(preview, dict)
    assert preview["dry_run"] is True
