"""Image-ingestion tools: upload, batch upload, delete, get, list batches.

All new in v0.3. The upload path runs every input through the
:mod:`roboflow_mcp.safety` pipeline before any HTTP call:

1. :mod:`~roboflow_mcp.safety.urlguard` — URL uploads only. Scheme
   allowlist, SSRF IP blocklist, streaming size cap.
2. :mod:`~roboflow_mcp.safety.paths` — local-path uploads only. Must live
   under ``ROBOFLOW_MCP_UPLOAD_ROOTS``; symlinks rejected.
3. :mod:`~roboflow_mcp.safety.imageguard` — every mode. Pillow verify +
   decode, MIME whitelist, dimension + size caps, decompression-bomb
   guard.

Only after all three pass do we reach :meth:`RoboflowClient.request_multipart`.
Retry is disabled on that code path because POSTs aren't idempotent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..audit import AuditLogger
from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..guards import destructive, is_tool_enabled, validate_bounds
from ..models.io import ImageSource, resolve_source
from ..models.upload import (
    BatchSummary,
    BatchUploadResult,
    DeleteResult,
    ImageDetail,
    UploadResult,
)
from ._common import dry_run_preview, resolve_workspace


async def upload_image_impl(
    project: str,
    source: ImageSource | dict[str, Any],
    *,
    workspace: str | None,
    split: str | None = None,
    batch_name: str | None = None,
    tag_names: list[str] | None = None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> UploadResult | dict[str, Any]:
    """Upload one image to a Roboflow project."""
    validate_bounds(
        {
            "project": project,
            "workspace": workspace,
            "split": split,
            "batch_name": batch_name,
            "tag_names": tag_names,
        },
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/dataset/{project}/upload"
    params: dict[str, Any] = {}
    if split:
        params["split"] = split
    if batch_name:
        params["batch"] = batch_name
    if tag_names:
        # Roboflow accepts repeat `tag=` params on upload.
        params["tag"] = list(tag_names)

    resolved = await resolve_source(source, settings)

    if dry_run:
        return dry_run_preview(
            "roboflow_upload_image",
            method="POST",
            path=path,
            params={**params, "api_key": "***"},
            body={
                "multipart_filename": resolved.filename,
                "multipart_bytes": len(resolved.content),
                "multipart_mime": resolved.info.mime,
                "workspace": slug,
            },
        )

    response = await client.request_multipart(
        "POST",
        path,
        files={"file": (resolved.filename, resolved.content, resolved.info.mime)},
        params=params,
    )

    payload = response if isinstance(response, dict) else {"raw": response}
    return UploadResult(
        id=payload.get("id"),
        image_id=payload.get("image", {}).get("id")
        if isinstance(payload.get("image"), dict)
        else None,
        success=bool(payload.get("success", True)),
        duplicate=bool(payload.get("duplicate", False)),
        split=split,
        filename=resolved.filename,
        project=project,
        raw=payload,
    )


async def upload_images_batch_impl(
    project: str,
    sources: Sequence[ImageSource | dict[str, Any]],
    *,
    workspace: str | None,
    split: str | None = None,
    batch_name: str | None = None,
    concurrency: int = 4,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> BatchUploadResult | dict[str, Any]:
    """Upload many images in parallel. Partial-failure tolerant."""
    if not sources:
        raise ValueError("sources must be a non-empty list")
    if len(sources) > settings.max_list_length:
        raise ValueError(
            f"sources list of {len(sources)} exceeds max_list_length="
            f"{settings.max_list_length}"
        )
    if concurrency < 1 or concurrency > 16:
        raise ValueError("concurrency must be between 1 and 16")

    if dry_run:
        slug = resolve_workspace(workspace, settings)
        return dry_run_preview(
            "roboflow_upload_images_batch",
            method="POST",
            path=f"/dataset/{project}/upload",
            body={
                "workspace": slug,
                "batch_size": len(sources),
                "split": split,
                "batch_name": batch_name,
                "concurrency": concurrency,
            },
        )

    semaphore = asyncio.Semaphore(concurrency)

    async def _one(src: ImageSource | dict[str, Any]) -> UploadResult | Exception:
        async with semaphore:
            try:
                result = await upload_image_impl(
                    project,
                    src,
                    workspace=workspace,
                    split=split,
                    batch_name=batch_name,
                    client=client,
                    settings=settings,
                )
                # dry_run is always False here, so result is UploadResult
                assert isinstance(result, UploadResult)
                return result
            except Exception as exc:
                return exc

    outcomes = await asyncio.gather(*(_one(s) for s in sources))
    results: list[UploadResult] = []
    errors: list[str] = []
    for outcome in outcomes:
        if isinstance(outcome, UploadResult):
            results.append(outcome)
        else:
            errors.append(f"{type(outcome).__name__}: {outcome}")
    return BatchUploadResult(
        total=len(sources),
        succeeded=len(results),
        failed=len(errors),
        results=results,
        errors=errors,
    )


@destructive
async def delete_image_impl(
    project: str,
    image_id: str,
    *,
    workspace: str | None,
    confirm: str = "",
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> DeleteResult | dict[str, Any]:
    """Delete one image from a project. Destructive: requires confirm='yes'."""
    validate_bounds(
        {"project": project, "image_id": image_id, "workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}/images/{image_id}"

    if dry_run:
        return dry_run_preview(
            "roboflow_delete_image",
            method="DELETE",
            path=path,
        )

    response = await client.request("DELETE", path)
    return DeleteResult(
        success=bool((response or {}).get("success", True))
        if isinstance(response, dict)
        else True,
        image_id=image_id,
        project=project,
        raw=response if isinstance(response, dict) else {"raw": str(response)},
    )


async def get_image_impl(
    project: str,
    image_id: str,
    *,
    workspace: str | None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> ImageDetail | dict[str, Any]:
    """Read a single image's metadata."""
    validate_bounds(
        {"project": project, "image_id": image_id, "workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}/images/{image_id}"

    if dry_run:
        return dry_run_preview("roboflow_get_image", method="GET", path=path)
    response = await client.request("GET", path)
    payload = response if isinstance(response, dict) else {"raw": response}
    image = payload.get("image", payload)
    return ImageDetail.model_validate({**image, "id": image_id, "raw": payload})


async def list_image_batches_impl(
    project: str,
    *,
    workspace: str | None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> list[BatchSummary] | dict[str, Any]:
    """List upload batches for a project."""
    validate_bounds(
        {"project": project, "workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}/batches"

    if dry_run:
        return dry_run_preview("roboflow_list_image_batches", method="GET", path=path)
    response = await client.request("GET", path)
    if not isinstance(response, dict):
        return []
    batches = response.get("batches") or response.get("results") or []
    return [BatchSummary.model_validate(b) for b in batches if isinstance(b, dict)]


def _register_tool(
    mcp: FastMCP,
    name: str,
    enabled: bool,
    func: Any,
) -> None:
    if enabled:
        mcp.tool()(func)


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
    audit: AuditLogger | None = None,
) -> None:
    """Register image-ingestion tools on the FastMCP instance."""

    from .image import _audited  # reuse the existing adapter

    if is_tool_enabled("roboflow_upload_image", settings):

        @mcp.tool()
        async def roboflow_upload_image(
            project: str,
            source: dict[str, Any],
            workspace: str | None = None,
            split: str | None = None,
            batch_name: str | None = None,
            tag_names: list[str] | None = None,
            dry_run: bool = False,
        ) -> UploadResult | dict[str, Any]:
            """Upload a single image to a Roboflow project.

            ``source`` is a discriminated union (exactly one mode):
            - ``{"kind": "url", "url": "https://..."}``
            - ``{"kind": "path", "path": "/abs/path/img.jpg"}`` (local
              path; must live under ROBOFLOW_MCP_UPLOAD_ROOTS)
            - ``{"kind": "base64", "data": "...", "filename": "img.jpg"}``

            Every mode runs through URL / path / image safety guards
            before the upload. ``split`` is "train" / "valid" / "test".
            """
            args = {
                "project": project,
                "source_kind": source.get("kind") if isinstance(source, dict) else None,
                "workspace": workspace,
                "split": split,
                "batch_name": batch_name,
                "tag_names": tag_names,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_upload_image", settings, workspace, args
            ) as span:
                result = await upload_image_impl(
                    project,
                    source,
                    workspace=workspace,
                    split=split,
                    batch_name=batch_name,
                    tag_names=tag_names,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_upload_images_batch", settings):

        @mcp.tool()
        async def roboflow_upload_images_batch(
            project: str,
            sources: list[dict[str, Any]],
            workspace: str | None = None,
            split: str | None = None,
            batch_name: str | None = None,
            concurrency: int = 4,
            dry_run: bool = False,
        ) -> BatchUploadResult | dict[str, Any]:
            """Upload many images concurrently.

            ``sources`` is a list of :class:`ImageSource` dicts. Failed
            uploads don't abort the batch; the response reports
            per-image outcomes in ``results`` and ``errors``.
            """
            args = {
                "project": project,
                "count": len(sources),
                "workspace": workspace,
                "split": split,
                "concurrency": concurrency,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_upload_images_batch", settings, workspace, args
            ) as span:
                result = await upload_images_batch_impl(
                    project,
                    sources,
                    workspace=workspace,
                    split=split,
                    batch_name=batch_name,
                    concurrency=concurrency,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_delete_image", settings):

        @mcp.tool()
        async def roboflow_delete_image(
            project: str,
            image_id: str,
            workspace: str | None = None,
            confirm: str = "",
            dry_run: bool = False,
        ) -> DeleteResult | dict[str, Any]:
            """Delete an image. Destructive: requires confirm='yes' and
            ROBOFLOW_MCP_MODE=curate or full."""
            args = {
                "project": project,
                "image_id": image_id,
                "workspace": workspace,
                "confirm": confirm,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_delete_image", settings, workspace, args
            ) as span:
                result = await delete_image_impl(
                    project,
                    image_id,
                    workspace=workspace,
                    confirm=confirm,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_get_image", settings):

        @mcp.tool()
        async def roboflow_get_image(
            project: str,
            image_id: str,
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> ImageDetail | dict[str, Any]:
            """Get the metadata of a single image."""
            args = {
                "project": project,
                "image_id": image_id,
                "workspace": workspace,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_get_image", settings, workspace, args
            ) as span:
                result = await get_image_impl(
                    project,
                    image_id,
                    workspace=workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_list_image_batches", settings):

        @mcp.tool()
        async def roboflow_list_image_batches(
            project: str,
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> list[BatchSummary] | dict[str, Any]:
            """List upload batches for a project."""
            args = {
                "project": project,
                "workspace": workspace,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_list_image_batches", settings, workspace, args
            ) as span:
                result = await list_image_batches_impl(
                    project,
                    workspace=workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result
