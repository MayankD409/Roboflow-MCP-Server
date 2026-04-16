"""Dataset-version lifecycle tools.

Six tools:

- ``roboflow_list_versions`` — enumerate versions under a project.
- ``roboflow_get_version`` — inspect one version (classes, splits, config).
- ``roboflow_create_version`` — kick off an async generation job. Quota-heavy,
  gated on ``ROBOFLOW_MCP_MODE=full`` and ``confirm='yes'``.
- ``roboflow_get_version_generation_status`` — poll an in-progress version.
- ``roboflow_export_version`` — get a signed download URL for a format.
- ``roboflow_delete_version`` — destructive; same guard as destructive tag ops.

The ``create`` / ``generate`` flow is **asynchronous server-side**: the POST
returns immediately with the version id, but the dataset zip isn't ready
for minutes. That's why the status endpoint exists. Tools stay on the
poll-and-return pattern — a caller inserts delay between attempts rather
than us blocking inside a tool call.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..audit import AuditLogger
from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..errors import NotFoundError
from ..guards import destructive, is_tool_enabled, validate_bounds
from ..models.upload import DeleteResult
from ..models.version import (
    ExportFormat,
    ExportResult,
    VersionDetail,
    VersionGenerationStatus,
    VersionSummary,
)
from ._common import dry_run_preview, resolve_workspace


async def list_versions_impl(
    project: str,
    *,
    workspace: str | None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> list[VersionSummary] | dict[str, Any]:
    validate_bounds(
        {"project": project, "workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}"
    if dry_run:
        return dry_run_preview(
            "roboflow_list_versions",
            method="GET",
            path=path,
            params={"resource": "versions"},
        )
    response = await client.request("GET", path)
    versions = (response or {}).get("versions") if isinstance(response, dict) else None
    if not isinstance(versions, list):
        return []
    result: list[VersionSummary] = []
    for v in versions:
        if not isinstance(v, dict):
            continue
        result.append(
            VersionSummary(
                id=str(v.get("id") or v.get("version") or ""),
                name=v.get("name"),
                created=v.get("created"),
                images=int(v.get("images", 0) or 0),
                trained=bool(v.get("model") or v.get("trained")),
            )
        )
    return result


async def get_version_impl(
    project: str,
    version: str,
    *,
    workspace: str | None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> VersionDetail | dict[str, Any]:
    validate_bounds(
        {"project": project, "version": version, "workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}/{version}"
    if dry_run:
        return dry_run_preview("roboflow_get_version", method="GET", path=path)
    response = await client.request("GET", path)
    payload = response if isinstance(response, dict) else {"raw": response}
    version_blob = payload.get("version", payload)
    return VersionDetail.model_validate(
        {**version_blob, "id": version_blob.get("id") or version, "raw": payload}
    )


@destructive
async def create_version_impl(
    project: str,
    *,
    workspace: str | None,
    preprocessing: dict[str, Any] | None = None,
    augmentation: dict[str, Any] | None = None,
    train_test_split: dict[str, int] | None = None,
    confirm: str = "",
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> dict[str, Any]:
    """Kick off an async generation. Quota-heavy."""
    validate_bounds(
        {"project": project, "workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}/generate"
    body: dict[str, Any] = {}
    if preprocessing:
        body["preprocessing"] = preprocessing
    if augmentation:
        body["augmentation"] = augmentation
    if train_test_split:
        body["split"] = train_test_split

    if dry_run:
        return dry_run_preview(
            "roboflow_create_version",
            method="POST",
            path=path,
            body=body,
        )
    response = await client.request("POST", path, json=body)
    # Response may include the new version id; surface it as-is so the
    # caller can immediately poll status.
    return {
        "project": project,
        "workspace": slug,
        "status": "generating",
        "raw": response if isinstance(response, dict) else {"raw": response},
    }


async def get_version_generation_status_impl(
    project: str,
    version: str,
    *,
    workspace: str | None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> VersionGenerationStatus | dict[str, Any]:
    validate_bounds(
        {"project": project, "version": version, "workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}/{version}"
    if dry_run:
        return dry_run_preview(
            "roboflow_get_version_generation_status", method="GET", path=path
        )
    try:
        response = await client.request("GET", path)
    except NotFoundError:
        # Roboflow returns 404 until the async pipeline writes the row.
        return VersionGenerationStatus(
            version=version, status="generating", message="Version not yet visible"
        )
    payload = response if isinstance(response, dict) else {"raw": response}
    version_blob = payload.get("version", payload)
    status: str
    if version_blob.get("generating"):
        status = "generating"
    elif version_blob.get("failed") or version_blob.get("error"):
        status = "failed"
    elif version_blob.get("id") or version_blob.get("images"):
        status = "ready"
    else:
        status = "unknown"
    return VersionGenerationStatus(
        version=version,
        status=status,
        progress=version_blob.get("progress"),
        message=version_blob.get("message"),
        raw=payload,
    )


async def export_version_impl(
    project: str,
    version: str,
    export_format: ExportFormat,
    *,
    workspace: str | None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> ExportResult | dict[str, Any]:
    validate_bounds(
        {
            "project": project,
            "version": version,
            "workspace": workspace,
        },
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}/{version}/{export_format}"
    if dry_run:
        return dry_run_preview("roboflow_export_version", method="GET", path=path)
    response = await client.request("GET", path)
    payload = response if isinstance(response, dict) else {"raw": response}
    link = (
        payload.get("export", {}).get("link")
        if isinstance(payload.get("export"), dict)
        else None
    )
    link = link or payload.get("link") or payload.get("url")
    return ExportResult(
        version=version,
        project=project,
        format=export_format,
        download_url=link,
        ready=bool(link),
        raw=payload,
    )


@destructive
async def delete_version_impl(
    project: str,
    version: str,
    *,
    workspace: str | None,
    confirm: str = "",
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> DeleteResult | dict[str, Any]:
    validate_bounds(
        {"project": project, "version": version, "workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}/{version}"
    if dry_run:
        return dry_run_preview("roboflow_delete_version", method="DELETE", path=path)
    response = await client.request("DELETE", path)
    return DeleteResult(
        success=bool((response or {}).get("success", True))
        if isinstance(response, dict)
        else True,
        version=version,
        project=project,
        raw=response if isinstance(response, dict) else {"raw": str(response)},
    )


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
    audit: AuditLogger | None = None,
) -> None:
    from .image import _audited

    if is_tool_enabled("roboflow_list_versions", settings):

        @mcp.tool()
        async def roboflow_list_versions(
            project: str,
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> list[VersionSummary] | dict[str, Any]:
            """List dataset versions under a project."""
            args = {"project": project, "workspace": workspace, "dry_run": dry_run}
            with _audited(
                audit, "roboflow_list_versions", settings, workspace, args
            ) as span:
                result = await list_versions_impl(
                    project,
                    workspace=workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_get_version", settings):

        @mcp.tool()
        async def roboflow_get_version(
            project: str,
            version: str,
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> VersionDetail | dict[str, Any]:
            """Read one version's full metadata."""
            args = {
                "project": project,
                "version": version,
                "workspace": workspace,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_get_version", settings, workspace, args
            ) as span:
                result = await get_version_impl(
                    project,
                    version,
                    workspace=workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_create_version", settings):

        @mcp.tool()
        async def roboflow_create_version(
            project: str,
            workspace: str | None = None,
            preprocessing: dict[str, Any] | None = None,
            augmentation: dict[str, Any] | None = None,
            train_test_split: dict[str, int] | None = None,
            confirm: str = "",
            dry_run: bool = False,
        ) -> dict[str, Any]:
            """Kick off an async version generation (quota-heavy).

            Destructive-of-quota: requires confirm='yes' and
            ROBOFLOW_MCP_MODE=curate or full. After this returns,
            poll ``roboflow_get_version_generation_status`` until the
            new version reports ``status="ready"``.
            """
            args = {
                "project": project,
                "workspace": workspace,
                "confirm": confirm,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_create_version", settings, workspace, args
            ) as span:
                result = await create_version_impl(
                    project,
                    workspace=workspace,
                    preprocessing=preprocessing,
                    augmentation=augmentation,
                    train_test_split=train_test_split,
                    confirm=confirm,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_get_version_generation_status", settings):

        @mcp.tool()
        async def roboflow_get_version_generation_status(
            project: str,
            version: str,
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> VersionGenerationStatus | dict[str, Any]:
            """Poll the async generation state of a version."""
            args = {
                "project": project,
                "version": version,
                "workspace": workspace,
                "dry_run": dry_run,
            }
            with _audited(
                audit,
                "roboflow_get_version_generation_status",
                settings,
                workspace,
                args,
            ) as span:
                result = await get_version_generation_status_impl(
                    project,
                    version,
                    workspace=workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_export_version", settings):

        @mcp.tool()
        async def roboflow_export_version(
            project: str,
            version: str,
            export_format: ExportFormat,
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> ExportResult | dict[str, Any]:
            """Request an export for a trained/generated version.

            Returns a signed download URL when ready. Does NOT stream
            bytes — pair with ``roboflow_download_export`` if you want
            the zip on disk.
            """
            args = {
                "project": project,
                "version": version,
                "export_format": export_format,
                "workspace": workspace,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_export_version", settings, workspace, args
            ) as span:
                result = await export_version_impl(
                    project,
                    version,
                    export_format,
                    workspace=workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_delete_version", settings):

        @mcp.tool()
        async def roboflow_delete_version(
            project: str,
            version: str,
            workspace: str | None = None,
            confirm: str = "",
            dry_run: bool = False,
        ) -> DeleteResult | dict[str, Any]:
            """Delete a dataset version. Destructive: confirm='yes' required."""
            args = {
                "project": project,
                "version": version,
                "workspace": workspace,
                "confirm": confirm,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_delete_version", settings, workspace, args
            ) as span:
                result = await delete_version_impl(
                    project,
                    version,
                    workspace=workspace,
                    confirm=confirm,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result
