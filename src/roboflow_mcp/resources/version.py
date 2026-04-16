"""``roboflow://workspace/{ws}/projects/{project}/versions/{version}`` resource.

Returns a human-readable Markdown summary of a dataset version. This is
the first MCP Resource we ship; it sets the pattern for workspace
(v0.5) and workflow (v0.6) resources.

We intentionally emit plaintext instead of JSON: resources are rendered
by MCP clients for humans to read, and a pre-formatted summary is more
useful than a raw dump. The LLM still has ``roboflow_get_version`` for
the structured shape.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..audit import AuditLogger
from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..guards import check_workspace_allowed
from ..safety.sanitize import sanitize_untrusted
from ..tools.version import get_version_impl


def _safe(value: Any) -> str:
    """Wrap an untrusted Roboflow string so the rendering client treats
    it as data, not instructions."""
    if value is None:
        return "(unset)"
    if not isinstance(value, str):
        value = str(value)
    wrapped = sanitize_untrusted(value)
    text = wrapped["untrusted"]
    return str(text)


async def render_version_summary(
    workspace: str,
    project: str,
    version: str,
    *,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> str:
    """Build the Markdown body for one version."""
    check_workspace_allowed(workspace, settings.workspace_allowlist)

    detail = await get_version_impl(
        project,
        version,
        workspace=workspace,
        client=client,
        settings=settings,
    )
    # get_version_impl with dry_run=False always returns VersionDetail
    from ..models.version import VersionDetail

    if not isinstance(detail, VersionDetail):
        return f"Could not fetch version {workspace}/{project}/{version}"

    lines: list[str] = [
        f"# Roboflow version `{_safe(workspace)}/{_safe(project)}/{_safe(version)}`",
        "",
        f"- **Name**: {_safe(detail.name)}",
        f"- **Created**: {_safe(detail.created)}",
        f"- **Total images**: {detail.images}",
        f"- **Trained**: {'yes' if detail.trained else 'no'}",
        f"- **Generating**: {'yes' if detail.generating else 'no'}",
    ]

    if detail.splits:
        lines.append("")
        lines.append("## Splits")
        for split_name, count in sorted(detail.splits.items()):
            lines.append(f"- {_safe(split_name)}: {count}")

    if detail.classes:
        lines.append("")
        lines.append("## Classes")
        for cls_name, count in sorted(
            detail.classes.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            lines.append(f"- {_safe(cls_name)}: {count}")

    if detail.preprocessing:
        lines.append("")
        lines.append("## Preprocessing")
        for step, value in sorted(detail.preprocessing.items()):
            lines.append(f"- {_safe(step)}: {_safe(value)}")

    if detail.augmentation:
        lines.append("")
        lines.append("## Augmentation")
        for step, value in sorted(detail.augmentation.items()):
            lines.append(f"- {_safe(step)}: {_safe(value)}")

    return "\n".join(lines)


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
    audit: AuditLogger | None = None,
) -> None:
    """Wire the resource into FastMCP."""

    @mcp.resource(
        uri="roboflow://workspace/{workspace}/projects/{project}/versions/{version}",
        name="Roboflow dataset version",
        description=(
            "Human-readable Markdown summary of a Roboflow dataset "
            "version. Includes split counts, class distribution, "
            "preprocessing + augmentation config."
        ),
    )
    async def version_resource(workspace: str, project: str, version: str) -> str:
        return await render_version_summary(
            workspace,
            project,
            version,
            client=client,
            settings=settings,
        )
