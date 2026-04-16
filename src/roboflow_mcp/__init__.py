"""mcp-server-roboflow: an MCP server that exposes the Roboflow API."""

from __future__ import annotations

from importlib import metadata

from .server import build_server, main

try:
    __version__: str = metadata.version("mcp-server-roboflow")
except metadata.PackageNotFoundError:  # pragma: no cover - uninstalled source checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__", "build_server", "main"]
