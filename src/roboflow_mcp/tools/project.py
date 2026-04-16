"""Project-read tool.

``roboflow_get_project`` is the one project-focused read. The rest of
the project domain (list) lives under ``workspace_tools`` since a
Roboflow workspace response already contains every project inline.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..audit import AuditLogger
from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..guards import is_tool_enabled, validate_bounds
from ..models.version import ProjectDetail
from ._common import dry_run_preview, resolve_workspace


async def get_project_impl(
    project: str,
    *,
    workspace: str | None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> ProjectDetail | dict[str, Any]:
    """Read one project's metadata from a workspace."""
    validate_bounds(
        {"project": project, "workspace": workspace},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}"

    if dry_run:
        return dry_run_preview("roboflow_get_project", method="GET", path=path)

    response = await client.request("GET", path)
    payload = response if isinstance(response, dict) else {"raw": response}
    project_blob = payload.get("project", payload)
    if not isinstance(project_blob, dict):
        project_blob = {}
    return ProjectDetail.model_validate(
        {
            **project_blob,
            "id": project_blob.get("id") or f"{slug}/{project}",
            "raw": payload,
        }
    )


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
    audit: AuditLogger | None = None,
) -> None:
    from .image import _audited

    if is_tool_enabled("roboflow_get_project", settings):

        @mcp.tool()
        async def roboflow_get_project(
            project: str,
            workspace: str | None = None,
            dry_run: bool = False,
        ) -> ProjectDetail | dict[str, Any]:
            """Read project metadata (classes, image count, splits)."""
            args = {"project": project, "workspace": workspace, "dry_run": dry_run}
            with _audited(
                audit, "roboflow_get_project", settings, workspace, args
            ) as span:
                result = await get_project_impl(
                    project,
                    workspace=workspace,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result
