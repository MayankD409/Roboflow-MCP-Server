"""MCP tool registrations.

Each module in this package exposes a ``register(mcp, client, settings)``
function that attaches its tools to the FastMCP instance. ``server.build_server``
imports and calls them in order during startup.
"""
