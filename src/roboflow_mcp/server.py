"""FastMCP application factory and CLI entry point.

``build_server`` wires settings, logging, an audit logger, a Roboflow HTTP
client, every tool module, and every resource together into a single
FastMCP instance. ``main()`` runs it over stdio so ``uvx
mcp-server-roboflow`` is all an MCP client needs.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .audit import AuditLogger
from .client import RoboflowClient
from .config import RoboflowSettings
from .logging import configure_logging
from .resources import version as version_resource
from .tools import annotation as annotation_tools
from .tools import download as download_tools
from .tools import image as image_tools
from .tools import project as project_tools
from .tools import upload as upload_tools
from .tools import version as version_tools
from .tools import workspace as workspace_tools

_INSTRUCTIONS = (
    "Hardened Roboflow MCP server (v0.3). Covers workspace/project read, "
    "image search + tag CRUD, image upload (URL / local path / base64), "
    "annotation upload (COCO / YOLO / Pascal VOC / CreateML / Roboflow "
    "JSON), project + version lifecycle, and streaming dataset export. "
    "Set ROBOFLOW_API_KEY in the environment. Destructive operations "
    "(remove/replace tags, delete image/version, download export) "
    "require ROBOFLOW_MCP_MODE=curate or full AND a literal "
    "confirm='yes' argument. Use dry_run=True to preview any tool "
    "without hitting the API. URL uploads go through an SSRF guard; "
    "path uploads go through a path-traversal guard and must live under "
    "ROBOFLOW_MCP_UPLOAD_ROOTS; every image is validated with Pillow "
    "before upload. Every invocation is recorded in the JSONL audit "
    "log at ROBOFLOW_MCP_AUDIT_LOG (stderr if unset)."
)


def build_server(
    settings: RoboflowSettings | None = None,
    *,
    client: RoboflowClient | None = None,
    audit: AuditLogger | None = None,
) -> FastMCP:
    """Create and configure the FastMCP application.

    Pass ``settings``, ``client``, and/or ``audit`` in tests; production
    callers rely on the defaults, which read settings from the environment
    and build fresh instances.
    """
    settings = settings or RoboflowSettings()
    configure_logging(
        settings.log_level,
        secret=settings.api_key.get_secret_value(),
    )
    http_client = client or RoboflowClient(settings)
    audit_logger = audit or AuditLogger(path=settings.audit_log_path)
    mcp = FastMCP(name="mcp-server-roboflow", instructions=_INSTRUCTIONS)

    # Tools
    workspace_tools.register(mcp, http_client, settings, audit=audit_logger)
    image_tools.register(mcp, http_client, settings, audit=audit_logger)
    upload_tools.register(mcp, http_client, settings, audit=audit_logger)
    annotation_tools.register(mcp, http_client, settings, audit=audit_logger)
    project_tools.register(mcp, http_client, settings, audit=audit_logger)
    version_tools.register(mcp, http_client, settings, audit=audit_logger)
    download_tools.register(mcp, http_client, settings, audit=audit_logger)

    # Resources
    version_resource.register(mcp, http_client, settings, audit=audit_logger)

    return mcp


def main() -> None:
    """CLI entry point; run the server over stdio."""
    mcp = build_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
