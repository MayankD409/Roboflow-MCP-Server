"""Helpers shared across tool modules."""

from __future__ import annotations

from typing import Any

from ..config import RoboflowSettings
from ..errors import ConfigurationError
from ..guards import check_workspace_allowed


def resolve_workspace(arg: str | None, settings: RoboflowSettings) -> str:
    """Return an explicit slug, falling back to ``ROBOFLOW_WORKSPACE``.

    Raises ``ConfigurationError`` if neither source provides a slug, and
    ``ToolDisabledError`` if a workspace allowlist is configured and the
    resolved slug isn't on it.
    """
    slug = arg or settings.workspace
    if not slug:
        raise ConfigurationError(
            "No workspace specified. Pass a workspace argument or set "
            "ROBOFLOW_WORKSPACE in the environment."
        )
    check_workspace_allowed(slug, settings.workspace_allowlist)
    return slug


def dry_run_preview(
    tool: str,
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: Any = None,
) -> dict[str, Any]:
    """Build the preview payload returned when ``dry_run=True``.

    Secrets in ``params`` are redacted so the preview is safe to print or
    forward to a client. This is the only function that constructs a dry-run
    response shape, so the schema stays consistent across every tool.
    """
    safe_params = _redact_params(params or {})
    return {
        "dry_run": True,
        "tool": tool,
        "method": method.upper(),
        "path": path,
        "params": safe_params,
        "body": body,
    }


def _redact_params(params: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in params.items():
        if key.lower() in {"api_key", "apikey", "authorization", "x-api-key"}:
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted
