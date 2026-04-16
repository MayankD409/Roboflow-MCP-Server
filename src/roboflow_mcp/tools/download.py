"""Export-download tool.

Exports are big (hundreds of MB to several GB), so we stream instead
of buffering. The destination lives under
``ROBOFLOW_MCP_EXPORT_CACHE_DIR`` by default so repeated exports don't
scatter zips across the user's filesystem.

Security invariants:

- ``download_url`` (if supplied by the caller) goes through the same
  SSRF guard used by URL-based image uploads. Roboflow's own export
  endpoint returns a signed URL on an amazonaws.com host; any private
  IP in the response means something is wrong.
- ``dest_dir`` (if supplied) must resolve **under**
  ``settings.export_cache_dir``. Arbitrary-write via LLM-controlled
  ``dest_dir`` is explicitly prevented.
- ``slug`` / ``project`` / ``version`` / ``export_format`` all go
  through a whitelist filter before being concatenated into a path,
  so a crafted slug like ``../../etc`` can't escape the cache dir.
- Extraction uses ``Path.is_relative_to`` (component-level, not
  string-prefix) to guard against zip-slip; entries with absolute paths
  or symlink file-mode bits are rejected outright.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..audit import AuditLogger
from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..errors import ConfigurationError
from ..guards import destructive, is_tool_enabled, validate_bounds
from ..models.version import DownloadResult, ExportFormat
from ..safety.urlguard import validate_url
from ._common import dry_run_preview, resolve_workspace

# Allow only letters, digits, underscore, hyphen inside filesystem
# components we compose from user input. Anything else becomes "_".
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_-]")

# Unix file-type bits for a symlink entry in a zip (upper 2 bytes of
# external_attr encode `st_mode`).
_ZIP_SYMLINK_MODE = 0o120000


def _sanitize_component(raw: str, *, field: str) -> str:
    cleaned = _SAFE_COMPONENT.sub("_", raw)
    cleaned = cleaned.strip("._") or "x"
    if len(cleaned) > 128:
        raise ConfigurationError(
            f"{field} too long after sanitisation ({len(cleaned)} chars); limit is 128."
        )
    return cleaned


def _resolve_cache_root(dest_dir: str | None, settings: RoboflowSettings) -> Path:
    """Return the directory the zip will be written to, confined to the
    configured export cache."""
    configured = settings.export_cache_dir.expanduser().resolve()
    configured.mkdir(parents=True, exist_ok=True)

    if dest_dir is None:
        return configured

    requested = Path(dest_dir).expanduser().resolve()
    # The caller may ask for a subdirectory of the cache root. Anything
    # outside is refused.
    try:
        requested.relative_to(configured)
    except ValueError as exc:
        raise ConfigurationError(
            f"dest_dir {requested} is not under "
            f"ROBOFLOW_MCP_EXPORT_CACHE_DIR={configured}. Pick a "
            "subdirectory of the cache or reconfigure the env var."
        ) from exc
    requested.mkdir(parents=True, exist_ok=True)
    return requested


def _extract_safely(zip_path: Path, extract_dir: Path) -> None:
    """Unzip with a component-level zip-slip guard + symlink rejection."""
    extract_dir_resolved = extract_dir.resolve()

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            member = info.filename

            # Absolute paths or parent-traversals in the member name
            # itself are rejected up front; don't trust `resolve()` to
            # clean them because `extract_dir / '/etc/passwd'` returns
            # `/etc/passwd` on Linux.
            if (
                member.startswith("/")
                or member.startswith("\\")
                or ".." in Path(member).parts
            ):
                raise ConfigurationError(
                    f"Refusing zip entry {member!r}: absolute or traversing path."
                )

            # Reject symlink entries — zipfile wouldn't honour them, but
            # a future extractor (SDK-backed, tarfile) would.
            unix_mode = info.external_attr >> 16
            if unix_mode & 0o170000 == _ZIP_SYMLINK_MODE:
                raise ConfigurationError(
                    f"Refusing zip entry {member!r}: symlink entries disallowed."
                )

            target = (extract_dir / member).resolve()
            if not target.is_relative_to(extract_dir_resolved):
                raise ConfigurationError(
                    f"Refusing zip entry {member!r}: destination outside "
                    "extract dir (zip-slip)."
                )

        zf.extractall(extract_dir)


@destructive
async def download_export_impl(
    project: str,
    version: str,
    export_format: ExportFormat,
    *,
    workspace: str | None,
    download_url: str | None = None,
    extract: bool = False,
    dest_dir: str | None = None,
    confirm: str = "",
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> DownloadResult | dict[str, Any]:
    """Stream a dataset export to local disk.

    If ``download_url`` is supplied we use it directly (caller already
    ran ``roboflow_export_version``); otherwise we ask Roboflow for
    one. Either way, the URL goes through the SSRF guard before any
    bytes cross the wire.

    Marked destructive-of-fs because the resulting tree can be large
    and writes to the user's filesystem under
    ``ROBOFLOW_MCP_EXPORT_CACHE_DIR``.
    """
    if not settings.enable_downloads:
        raise ConfigurationError(
            "Dataset downloads are disabled. "
            "Set ROBOFLOW_MCP_ENABLE_DOWNLOADS=true to enable."
        )

    validate_bounds(
        {
            "project": project,
            "version": version,
            "workspace": workspace,
            "download_url": download_url,
            "dest_dir": dest_dir,
        },
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    cache_root = _resolve_cache_root(dest_dir, settings)

    # Compose the zip filename from sanitised pieces so a path-separator
    # character smuggled into slug / project / version can't escape.
    safe_name = "__".join(
        _sanitize_component(c, field=name)
        for c, name in (
            (slug, "slug"),
            (project, "project"),
            (version, "version"),
            (export_format, "export_format"),
        )
    )
    zip_path = cache_root / f"{safe_name}.zip"

    if dry_run:
        return dry_run_preview(
            "roboflow_download_export",
            method="GET",
            path=f"/{slug}/{project}/{version}/{export_format}",
            body={
                "zip_path": str(zip_path),
                "extract": extract,
                "extract_path": str(cache_root / safe_name) if extract else None,
            },
        )

    # If we don't have a link, ask Roboflow for one.
    if download_url is None:
        api_response = await client.request(
            "GET", f"/{slug}/{project}/{version}/{export_format}"
        )
        link = None
        if isinstance(api_response, dict):
            export = api_response.get("export") or {}
            link = export.get("link") if isinstance(export, dict) else None
            link = link or api_response.get("link") or api_response.get("url")
        if not link:
            raise ConfigurationError(
                "Roboflow did not return a download link. The version may "
                "not be ready yet — try again after generation completes."
            )
        download_url = link

    # SSRF-guard the download URL — even the one Roboflow returned,
    # because that URL is signed-but-opaque and we don't want this
    # code path to be the one place an operator-controlled URL can
    # reach internal IPs.
    await validate_url(download_url, allow_insecure=settings.allow_insecure)

    bytes_written = await client.stream_to_file(
        "GET",
        download_url,
        dest=zip_path,
        max_bytes=None,  # large exports are fine; filesystem limits apply
    )

    extracted = False
    if extract:
        extract_dir = cache_root / safe_name
        extract_dir.mkdir(parents=True, exist_ok=True)
        _extract_safely(zip_path, extract_dir)
        extracted = True

    return DownloadResult(
        version=version,
        project=project,
        format=export_format,
        path=str(zip_path),
        bytes=bytes_written,
        extracted=extracted,
    )


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
    audit: AuditLogger | None = None,
) -> None:
    from .image import _audited

    if is_tool_enabled("roboflow_download_export", settings):

        @mcp.tool()
        async def roboflow_download_export(
            project: str,
            version: str,
            export_format: ExportFormat,
            workspace: str | None = None,
            download_url: str | None = None,
            extract: bool = False,
            dest_dir: str | None = None,
            confirm: str = "",
            dry_run: bool = False,
        ) -> DownloadResult | dict[str, Any]:
            """Stream an exported dataset zip to disk.

            Writes under ROBOFLOW_MCP_EXPORT_CACHE_DIR (default
            ``~/.cache/roboflow-mcp``). ``dest_dir``, when given, must be
            a subdirectory of the cache root.

            Destructive-to-fs: requires confirm='yes' and
            ROBOFLOW_MCP_MODE=curate or full.
            """
            args = {
                "project": project,
                "version": version,
                "export_format": export_format,
                "workspace": workspace,
                "extract": extract,
                "has_dest_dir": dest_dir is not None,
                "confirm": confirm,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_download_export", settings, workspace, args
            ) as span:
                result = await download_export_impl(
                    project,
                    version,
                    export_format,
                    workspace=workspace,
                    download_url=download_url,
                    extract=extract,
                    dest_dir=dest_dir,
                    confirm=confirm,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result
