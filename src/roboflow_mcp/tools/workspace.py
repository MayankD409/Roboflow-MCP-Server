"""Workspace tools: inspect a Roboflow workspace and list its projects.

Two tools are exposed. Both hit ``GET /{workspace}`` under the hood; the
``list_projects`` tool exists as a lighter-weight option when callers only
care about the project list. Both are read-only and therefore safe in any
server mode (including ``readonly``).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..audit import AuditLogger
from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..guards import is_tool_enabled, validate_bounds
from ..models.workspace import Project, Workspace
from ._common import dry_run_preview, resolve_workspace


async def get_workspace_impl(
    workspace: str | None,
    *,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> Workspace | dict[str, Any]:
    """Fetch a workspace and parse it into a ``Workspace`` model."""
    validate_bounds(
        {"workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    if dry_run:
        return dry_run_preview(
            "roboflow_get_workspace",
            method="GET",
            path=f"/{slug}",
        )
    data = await client.request("GET", f"/{slug}")
    return Workspace.model_validate(data["workspace"])


async def list_projects_impl(
    workspace: str | None,
    *,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> list[Project] | dict[str, Any]:
    """Return just the projects list from a workspace."""
    result = await get_workspace_impl(
        workspace,
        dry_run=dry_run,
        client=client,
        settings=settings,
    )
    if isinstance(result, Workspace):
        return result.projects
    return result  # dry_run preview dict


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
    audit: AuditLogger | None = None,
) -> None:
    """Attach the workspace tools to ``mcp``.

    Tools excluded by ``ROBOFLOW_MCP_ALLOW_TOOLS`` or
    ``ROBOFLOW_MCP_DENY_TOOLS`` are not registered at all, so they don't
    appear in ``list_tools`` responses.
    """

    if is_tool_enabled("roboflow_get_workspace", settings):

        @mcp.tool()
        async def roboflow_get_workspace(
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> Workspace | dict[str, Any]:
            """Get a Roboflow workspace's metadata and its projects.

            Pass ``workspace`` to override the default set in
            ``ROBOFLOW_WORKSPACE``. Set ``dry_run=True`` to preview the HTTP
            request without calling the API.
            """
            args = {"workspace": workspace, "dry_run": dry_run}
            if audit is None:
                return await get_workspace_impl(
                    workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
            with audit.span(
                tool="roboflow_get_workspace",
                mode=settings.mode.value,
                workspace=workspace or settings.workspace,
                args=args,
            ) as span:
                result = await get_workspace_impl(
                    workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_list_projects", settings):

        @mcp.tool()
        async def roboflow_list_projects(
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> list[Project] | dict[str, Any]:
            """List all projects in a Roboflow workspace.

            Lighter than ``roboflow_get_workspace`` when you only need the
            project list. Pass ``workspace`` to override
            ``ROBOFLOW_WORKSPACE``. Set ``dry_run=True`` to preview.
            """
            args = {"workspace": workspace, "dry_run": dry_run}
            if audit is None:
                return await list_projects_impl(
                    workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
            with audit.span(
                tool="roboflow_list_projects",
                mode=settings.mode.value,
                workspace=workspace or settings.workspace,
                args=args,
            ) as span:
                result = await list_projects_impl(
                    workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result
