"""Capability model for tools.

Three primitives live here:

1. :func:`check_tool_allowed` — enforces the allow/deny lists.
2. :func:`check_workspace_allowed` — enforces the per-workspace scope lock.
3. :func:`destructive` — a decorator that refuses to run in readonly mode
   and requires ``confirm="yes"`` when called.

The goal is defense in depth: even if an LLM is tricked into calling a
destructive tool, it still needs (a) the operator to have enabled the
appropriate mode and (b) to supply the exact confirm token. Both failures
raise typed exceptions the MCP layer surfaces to the caller.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from .config import RoboflowSettings, ServerMode
from .errors import ConfigurationError, ToolDisabledError

T = TypeVar("T")

# Deliberately a plaintext user-facing confirmation string, not a secret.
# Any prompt-injection that reads "set confirm=true" fails the exact-match
# check; the token has to be typed literally by the operator / LLM call site.
CONFIRM_TOKEN = "yes"  # nosec B105 - confirmation token, not a password


def check_tool_allowed(
    tool_name: str,
    *,
    allow: frozenset[str],
    deny: frozenset[str],
) -> None:
    """Raise :class:`ToolDisabledError` if the tool is not allowed.

    Deny list wins over allow list: if both lists contain the name, the tool
    is rejected. An empty allow list means "allow all" (no allowlist
    configured); an empty deny list means "deny none".
    """
    if deny and tool_name in deny:
        raise ToolDisabledError(
            f"Tool {tool_name!r} is disabled by ROBOFLOW_MCP_DENY_TOOLS"
        )
    if allow and tool_name not in allow:
        raise ToolDisabledError(
            f"Tool {tool_name!r} is not listed in ROBOFLOW_MCP_ALLOW_TOOLS"
        )


def check_workspace_allowed(
    workspace: str,
    allowlist: frozenset[str],
) -> None:
    """Raise if ``workspace`` isn't in a non-empty allowlist."""
    if allowlist and workspace not in allowlist:
        raise ToolDisabledError(
            f"Workspace {workspace!r} is not in ROBOFLOW_MCP_WORKSPACE_ALLOWLIST"
        )


def is_tool_enabled(tool_name: str, settings: RoboflowSettings) -> bool:
    """Convenience helper for registration-time filtering.

    Returns False if the tool is excluded by the allow/deny lists; True
    otherwise. Does not inspect mode — destructive tools should still be
    registered in readonly mode so they can surface a clear error.
    """
    try:
        check_tool_allowed(
            tool_name,
            allow=settings.allow_tools,
            deny=settings.deny_tools,
        )
    except ToolDisabledError:
        return False
    return True


def destructive(
    func: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """Mark a tool implementation as destructive.

    The wrapped coroutine will:
    - Refuse to run when ``settings.mode == ServerMode.READONLY``.
    - Require a keyword argument ``confirm="yes"``.

    Both settings and confirm are expected as keyword arguments on the
    wrapped function — the convention the existing ``*_impl`` helpers use.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        settings: RoboflowSettings | None = kwargs.get("settings")
        if settings is None:
            raise ConfigurationError(
                f"{func.__name__}: destructive tool called without settings; "
                "this is a bug — tool registrations must forward settings."
            )
        if not ServerMode.allows_destructive(settings.mode):
            raise ToolDisabledError(
                f"{func.__name__}: destructive operations are blocked in "
                f"mode={settings.mode.value!r}. Set ROBOFLOW_MCP_MODE=curate "
                f"or full to enable."
            )
        confirm = kwargs.get("confirm")
        if confirm != CONFIRM_TOKEN:
            raise ConfigurationError(
                f"{func.__name__}: destructive operations require "
                f"confirm='{CONFIRM_TOKEN}' (got {confirm!r})."
            )
        return await func(*args, **kwargs)

    wrapper._roboflow_mcp_destructive = True  # type: ignore[attr-defined]
    return wrapper


def validate_bounds(
    values: dict[str, Any],
    *,
    max_string: int,
    max_list: int,
) -> None:
    """Raise ``ValueError`` if any string or list field exceeds bounds.

    Only inspects top-level values; nested structures are left alone. This
    is a cheap pre-HTTP gate, not a full schema validator — pydantic is the
    real validator on the way into each tool.
    """
    for key, value in values.items():
        if isinstance(value, str) and len(value) > max_string:
            raise ValueError(
                f"{key!r} exceeds {max_string} characters (got {len(value)})."
            )
        if isinstance(value, (list, tuple)) and len(value) > max_list:
            raise ValueError(f"{key!r} exceeds {max_list} items (got {len(value)}).")
