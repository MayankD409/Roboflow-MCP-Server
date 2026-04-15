"""Workspace tools: inspect a Roboflow workspace and list its projects.

Two tools are exposed. Both hit ``GET /{workspace}`` under the hood; the
``list_projects`` tool exists as a lighter-weight option when callers only
care about the project list.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..models.workspace import Project, Workspace
from ._common import resolve_workspace


async def get_workspace_impl(
    workspace: str | None,
    *,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> Workspace:
    """Fetch a workspace and parse it into a ``Workspace`` model."""
    slug = resolve_workspace(workspace, settings)
    data = await client.request("GET", f"/{slug}")
    return Workspace.model_validate(data["workspace"])


async def list_projects_impl(
    workspace: str | None,
    *,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> list[Project]:
    """Return just the projects list from a workspace."""
    ws = await get_workspace_impl(workspace, client=client, settings=settings)
    return ws.projects


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> None:
    """Attach the workspace tools to ``mcp``."""

    @mcp.tool()
    async def roboflow_get_workspace(workspace: str | None = None) -> Workspace:
        """Get a Roboflow workspace's metadata and its projects.

        Pass ``workspace`` to override the default set in ``ROBOFLOW_WORKSPACE``.
        """
        return await get_workspace_impl(workspace, client=client, settings=settings)

    @mcp.tool()
    async def roboflow_list_projects(workspace: str | None = None) -> list[Project]:
        """List all projects in a Roboflow workspace.

        Lighter than ``roboflow_get_workspace`` when you only need the project
        list. Pass ``workspace`` to override ``ROBOFLOW_WORKSPACE``.
        """
        return await list_projects_impl(workspace, client=client, settings=settings)
