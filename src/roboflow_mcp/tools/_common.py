"""Helpers shared across tool modules."""

from __future__ import annotations

from ..config import RoboflowSettings
from ..errors import ConfigurationError


def resolve_workspace(arg: str | None, settings: RoboflowSettings) -> str:
    """Return an explicit slug, falling back to ``ROBOFLOW_WORKSPACE``.

    Raises ``ConfigurationError`` if neither source provides a slug.
    """
    slug = arg or settings.workspace
    if not slug:
        raise ConfigurationError(
            "No workspace specified. Pass a workspace argument or set "
            "ROBOFLOW_WORKSPACE in the environment."
        )
    return slug
