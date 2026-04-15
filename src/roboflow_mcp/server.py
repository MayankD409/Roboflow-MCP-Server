"""FastMCP application factory and CLI entry point.

``build_server`` wires settings, logging, a Roboflow HTTP client, and every
tool module together into a single FastMCP instance. ``main()`` runs it over
stdio so ``uvx mcp-server-roboflow`` is all an MCP client needs.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import RoboflowClient
from .config import RoboflowSettings
from .logging import configure_logging
from .tools import image as image_tools
from .tools import workspace as workspace_tools

_INSTRUCTIONS = (
    "Thin wrapper around the Roboflow API. Use the tools exposed here to "
    "inspect workspaces and projects, upload and tag images, and manage "
    "annotations. Set ROBOFLOW_API_KEY in the environment before calling any "
    "tool."
)


def build_server(
    settings: RoboflowSettings | None = None,
    *,
    client: RoboflowClient | None = None,
) -> FastMCP:
    """Create and configure the FastMCP application.

    Pass ``settings`` and/or ``client`` in tests; production callers rely on
    the defaults, which read settings from the environment and build a fresh
    ``RoboflowClient``.
    """
    settings = settings or RoboflowSettings()
    configure_logging(
        settings.log_level,
        secret=settings.api_key.get_secret_value(),
    )
    http_client = client or RoboflowClient(settings)
    mcp = FastMCP(name="mcp-server-roboflow", instructions=_INSTRUCTIONS)

    workspace_tools.register(mcp, http_client, settings)
    image_tools.register(mcp, http_client, settings)

    return mcp


def main() -> None:
    """CLI entry point; run the server over stdio."""
    mcp = build_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
