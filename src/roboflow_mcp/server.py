"""FastMCP application factory and CLI entry point.

Phase 1 ships the skeleton only: a properly-named FastMCP instance with
logging configured and no tools registered. Tool modules will import the
server and attach themselves via ``@mcp.tool`` starting in Phase 2.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import RoboflowSettings
from .logging import configure_logging

_INSTRUCTIONS = (
    "Thin wrapper around the Roboflow API. Use the tools exposed here to "
    "inspect workspaces and projects, upload and tag images, and manage "
    "annotations. Set ROBOFLOW_API_KEY in the environment before calling any "
    "tool."
)


def build_server(settings: RoboflowSettings | None = None) -> FastMCP:
    """Create and configure the FastMCP application.

    Pass ``settings`` explicitly in tests; in production we read from env.
    """
    settings = settings or RoboflowSettings()
    configure_logging(
        settings.log_level,
        secret=settings.api_key.get_secret_value(),
    )
    return FastMCP(name="mcp-server-roboflow", instructions=_INSTRUCTIONS)


def main() -> None:
    """CLI entry point; run the server over stdio."""
    mcp = build_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
