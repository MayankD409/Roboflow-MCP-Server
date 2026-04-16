"""Image search and tagging tools.

Covers the read and tag half of the image domain:

- ``roboflow_search_images`` -- project-level search with tag, class, and
  semantic-prompt filters. Read-only.
- ``roboflow_add_image_tags`` -- additive tag write. Writeable in ``curate``
  or ``full`` mode.
- ``roboflow_remove_image_tags`` / ``roboflow_set_image_tags`` --
  destructive tag writes (they destroy tag state that existed on the
  image). Guarded by :func:`roboflow_mcp.guards.destructive`: require
  ``confirm='yes'`` and a non-readonly mode.

Upload and deletion live in their own modules to keep this file focused.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..audit import AuditLogger
from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..guards import destructive, is_tool_enabled, validate_bounds
from ..models.image import ImageSearchResult
from ._common import dry_run_preview, resolve_workspace

_DEFAULT_FIELDS: list[str] = ["id", "name", "tags", "split", "created"]
_MAX_LIMIT = 250
_MIN_LIMIT = 1

_TagOperation = Literal["add", "remove", "set"]


async def search_images_impl(
    project: str,
    *,
    workspace: str | None,
    tag: str | None = None,
    prompt: str | None = None,
    class_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> ImageSearchResult | dict[str, Any]:
    """Search a project's images with optional tag / class / prompt filters."""
    validate_bounds(
        {
            "project": project,
            "workspace": workspace,
            "tag": tag,
            "prompt": prompt,
            "class_name": class_name,
            "fields": fields,
        },
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    body: dict[str, Any] = {
        "limit": _clamp_limit(limit),
        "offset": max(offset, 0),
        "fields": list(fields) if fields else list(_DEFAULT_FIELDS),
    }
    if tag:
        body["tag"] = tag
    if prompt:
        body["prompt"] = prompt
    if class_name:
        body["class_name"] = class_name

    path = f"/{slug}/{project}/search"
    if dry_run:
        return dry_run_preview(
            "roboflow_search_images",
            method="POST",
            path=path,
            body=body,
        )
    data = await client.request("POST", path, json=body)
    return ImageSearchResult.model_validate(data)


async def _tag_op(
    operation: _TagOperation,
    project: str,
    image_id: str,
    tags: list[str],
    *,
    workspace: str | None,
    dry_run: bool,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> dict[str, Any]:
    if not tags:
        raise ValueError("tags must be a non-empty list")
    validate_bounds(
        {
            "project": project,
            "image_id": image_id,
            "workspace": workspace,
            "tags": tags,
        },
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    body = {"operation": operation, "tags": list(tags)}
    path = f"/{slug}/{project}/images/{image_id}/tags"
    if dry_run:
        return dry_run_preview(
            f"roboflow_{operation}_image_tags",
            method="POST",
            path=path,
            body=body,
        )
    response = await client.request("POST", path, json=body)
    return {
        "image_id": image_id,
        "project": project,
        "operation": operation,
        "tags": list(tags),
        "response": response,
    }


async def add_image_tags_impl(
    project: str,
    image_id: str,
    tags: list[str],
    *,
    workspace: str | None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> dict[str, Any]:
    """Attach tags to a single image. Additive, not destructive."""
    return await _tag_op(
        "add",
        project,
        image_id,
        tags,
        workspace=workspace,
        dry_run=dry_run,
        client=client,
        settings=settings,
    )


@destructive
async def remove_image_tags_impl(
    project: str,
    image_id: str,
    tags: list[str],
    *,
    workspace: str | None,
    confirm: str = "",
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> dict[str, Any]:
    """Detach tags from a single image. Destructive: requires ``confirm='yes'``."""
    return await _tag_op(
        "remove",
        project,
        image_id,
        tags,
        workspace=workspace,
        dry_run=dry_run,
        client=client,
        settings=settings,
    )


@destructive
async def set_image_tags_impl(
    project: str,
    image_id: str,
    tags: list[str],
    *,
    workspace: str | None,
    confirm: str = "",
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> dict[str, Any]:
    """Replace all tags on an image. Destructive: requires ``confirm='yes'``."""
    return await _tag_op(
        "set",
        project,
        image_id,
        tags,
        workspace=workspace,
        dry_run=dry_run,
        client=client,
        settings=settings,
    )


def _clamp_limit(limit: int) -> int:
    return max(_MIN_LIMIT, min(limit, _MAX_LIMIT))


def _audited(
    audit: AuditLogger | None,
    tool: str,
    settings: RoboflowSettings,
    workspace: str | None,
    args: dict[str, Any],
) -> AbstractContextManager[Any]:
    """Context-manager adapter: real audit span if enabled, no-op otherwise."""
    if audit is None:
        return _nullcontext()
    return audit.span(
        tool=tool,
        mode=settings.mode.value,
        workspace=workspace or settings.workspace,
        args=args,
    )


class _nullcontext:
    """Minimal no-op context manager used when audit logging is disabled."""

    def __enter__(self) -> _NullSpan:
        return _NullSpan()

    def __exit__(self, *_: object) -> None:
        return None


class _NullSpan:
    outcome: str = "ok"
    http_status: int | None = None


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
    audit: AuditLogger | None = None,
) -> None:
    """Attach the image search and tag tools to ``mcp``."""

    if is_tool_enabled("roboflow_search_images", settings):

        @mcp.tool()
        async def roboflow_search_images(
            project: str,
            workspace: str | None = None,
            tag: str | None = None,
            prompt: str | None = None,
            class_name: str | None = None,
            limit: int = 50,
            offset: int = 0,
            fields: list[str] | None = None,
            dry_run: bool = False,
        ) -> ImageSearchResult | dict[str, Any]:
            """Search images in a Roboflow project.

            Filter by ``tag`` (e.g. "sku-42"), ``class_name``, or a semantic
            ``prompt``. Paginated via ``limit`` (max 250) and ``offset``.
            ``workspace`` falls back to ``ROBOFLOW_WORKSPACE``. Set
            ``dry_run=True`` to preview the HTTP request without calling.
            """
            args = {
                "project": project,
                "workspace": workspace,
                "tag": tag,
                "prompt": prompt,
                "class_name": class_name,
                "limit": limit,
                "offset": offset,
                "fields": fields,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_search_images", settings, workspace, args
            ) as span:
                result = await search_images_impl(
                    project,
                    workspace=workspace,
                    tag=tag,
                    prompt=prompt,
                    class_name=class_name,
                    limit=limit,
                    offset=offset,
                    fields=fields,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_add_image_tags", settings):

        @mcp.tool()
        async def roboflow_add_image_tags(
            project: str,
            image_id: str,
            tags: list[str],
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> dict[str, Any]:
            """Add one or more tags to an image. Additive; not destructive."""
            args = {
                "project": project,
                "image_id": image_id,
                "tags": tags,
                "workspace": workspace,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_add_image_tags", settings, workspace, args
            ) as span:
                result = await add_image_tags_impl(
                    project,
                    image_id,
                    tags,
                    workspace=workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_remove_image_tags", settings):

        @mcp.tool()
        async def roboflow_remove_image_tags(
            project: str,
            image_id: str,
            tags: list[str],
            workspace: str | None = None,
            confirm: str = "",
            dry_run: bool = False,
        ) -> dict[str, Any]:
            """Remove tags from an image.

            Destructive: requires ``confirm='yes'`` and a server mode of
            ``curate`` or ``full`` (see :envvar:`ROBOFLOW_MCP_MODE`).
            """
            args = {
                "project": project,
                "image_id": image_id,
                "tags": tags,
                "workspace": workspace,
                "confirm": confirm,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_remove_image_tags", settings, workspace, args
            ) as span:
                result = await remove_image_tags_impl(
                    project,
                    image_id,
                    tags,
                    workspace=workspace,
                    confirm=confirm,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_set_image_tags", settings):

        @mcp.tool()
        async def roboflow_set_image_tags(
            project: str,
            image_id: str,
            tags: list[str],
            workspace: str | None = None,
            confirm: str = "",
            dry_run: bool = False,
        ) -> dict[str, Any]:
            """Replace an image's tags with the given list.

            Destructive: requires ``confirm='yes'`` and a server mode of
            ``curate`` or ``full`` (see :envvar:`ROBOFLOW_MCP_MODE`).
            """
            args = {
                "project": project,
                "image_id": image_id,
                "tags": tags,
                "workspace": workspace,
                "confirm": confirm,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_set_image_tags", settings, workspace, args
            ) as span:
                result = await set_image_tags_impl(
                    project,
                    image_id,
                    tags,
                    workspace=workspace,
                    confirm=confirm,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result
