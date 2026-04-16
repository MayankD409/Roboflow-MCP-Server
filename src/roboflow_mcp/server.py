"""FastMCP application factory and CLI entry point.

``build_server`` wires settings, logging, an audit logger, a Roboflow HTTP
client, and every tool module together into a single FastMCP instance.
``main()`` runs it over stdio so ``uvx mcp-server-roboflow`` is all an MCP
client needs.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .audit import AuditLogger
from .client import RoboflowClient
from .config import RoboflowSettings
from .logging import configure_logging
from .tools import image as image_tools
from .tools import workspace as workspace_tools

_INSTRUCTIONS = (
    "Thin wrapper around the Roboflow API. Use the tools exposed here to "
    "inspect workspaces and projects, upload and tag images, and manage "
    "annotations. Set ROBOFLOW_API_KEY in the environment before calling any "
    "tool. Destructive operations (removing / replacing tags, future "
    "deletes) require ROBOFLOW_MCP_MODE=curate or full and a confirm='yes' "
    "argument. Use dry_run=True to preview a request without calling the "
    "API. Every tool invocation is recorded in the JSONL audit log at "
    "ROBOFLOW_MCP_AUDIT_LOG (stderr if unset)."
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

    workspace_tools.register(mcp, http_client, settings, audit=audit_logger)
    image_tools.register(mcp, http_client, settings, audit=audit_logger)

    return mcp


def main() -> None:
    """CLI entry point; run the server over stdio."""
    mcp = build_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
