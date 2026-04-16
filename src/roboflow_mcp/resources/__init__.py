"""Read-only MCP resources.

Tools are action-oriented; resources are data-oriented. The first one,
:mod:`version`, exposes dataset-version summaries as browseable
``roboflow://`` URIs so an MCP client's resource UI can show them
without the LLM having to call a tool.
"""

from . import version as version_resource

__all__ = ["version_resource"]
