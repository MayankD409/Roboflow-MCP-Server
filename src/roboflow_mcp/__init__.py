"""mcp-server-roboflow: an MCP server that exposes the Roboflow API."""

from .server import build_server, main

__version__ = "0.1.1"
__all__ = ["__version__", "build_server", "main"]
