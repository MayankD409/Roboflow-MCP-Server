"""Image search and tagging tools.

Covers the read and tag half of the image domain:

- ``roboflow_search_images`` -- project-level search with tag, class, and
  semantic-prompt filters.
- ``roboflow_add_image_tags`` / ``roboflow_remove_image_tags`` /
  ``roboflow_set_image_tags`` -- thin wrappers over the single
  ``POST /{ws}/{project}/images/{id}/tags`` endpoint so each operation
  surfaces as its own tool (easier for an LLM to pick).

Upload and deletion live in their own modules to keep this file focused.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..models.image import ImageSearchResult
from ._common import resolve_workspace

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
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> ImageSearchResult:
    """Search a project's images with optional tag / class / prompt filters."""
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

    data = await client.request("POST", f"/{slug}/{project}/search", json=body)
    return ImageSearchResult.model_validate(data)


async def _tag_op(
    operation: _TagOperation,
    project: str,
    image_id: str,
    tags: list[str],
    *,
    workspace: str | None,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> dict[str, Any]:
    if not tags:
        raise ValueError("tags must be a non-empty list")
    slug = resolve_workspace(workspace, settings)
    body = {"operation": operation, "tags": list(tags)}
    path = f"/{slug}/{project}/images/{image_id}/tags"
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
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> dict[str, Any]:
    """Attach tags to a single image."""
    return await _tag_op(
        "add",
        project,
        image_id,
        tags,
        workspace=workspace,
        client=client,
        settings=settings,
    )


async def remove_image_tags_impl(
    project: str,
    image_id: str,
    tags: list[str],
    *,
    workspace: str | None,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> dict[str, Any]:
    """Detach tags from a single image."""
    return await _tag_op(
        "remove",
        project,
        image_id,
        tags,
        workspace=workspace,
        client=client,
        settings=settings,
    )


async def set_image_tags_impl(
    project: str,
    image_id: str,
    tags: list[str],
    *,
    workspace: str | None,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> dict[str, Any]:
    """Replace all tags on an image with the given list."""
    return await _tag_op(
        "set",
        project,
        image_id,
        tags,
        workspace=workspace,
        client=client,
        settings=settings,
    )


def _clamp_limit(limit: int) -> int:
    return max(_MIN_LIMIT, min(limit, _MAX_LIMIT))


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> None:
    """Attach the image search and tag tools to ``mcp``."""

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
    ) -> ImageSearchResult:
        """Search images in a Roboflow project.

        Filter by ``tag`` (e.g. "sku-42"), ``class_name``, or a semantic
        ``prompt``. Results are paginated via ``limit`` (max 250) and
        ``offset``. ``workspace`` falls back to ``ROBOFLOW_WORKSPACE``.
        """
        return await search_images_impl(
            project,
            workspace=workspace,
            tag=tag,
            prompt=prompt,
            class_name=class_name,
            limit=limit,
            offset=offset,
            fields=fields,
            client=client,
            settings=settings,
        )

    @mcp.tool()
    async def roboflow_add_image_tags(
        project: str,
        image_id: str,
        tags: list[str],
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Add one or more tags to an image."""
        return await add_image_tags_impl(
            project,
            image_id,
            tags,
            workspace=workspace,
            client=client,
            settings=settings,
        )

    @mcp.tool()
    async def roboflow_remove_image_tags(
        project: str,
        image_id: str,
        tags: list[str],
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Remove one or more tags from an image."""
        return await remove_image_tags_impl(
            project,
            image_id,
            tags,
            workspace=workspace,
            client=client,
            settings=settings,
        )

    @mcp.tool()
    async def roboflow_set_image_tags(
        project: str,
        image_id: str,
        tags: list[str],
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Replace an image's tags with exactly the given list."""
        return await set_image_tags_impl(
            project,
            image_id,
            tags,
            workspace=workspace,
            client=client,
            settings=settings,
        )
