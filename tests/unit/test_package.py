"""Smoke tests for the package itself. Prove the scaffold is import-clean."""

from __future__ import annotations

from importlib import metadata

import roboflow_mcp


def test_version_is_a_string() -> None:
    assert isinstance(roboflow_mcp.__version__, str)
    assert roboflow_mcp.__version__


def test_version_matches_installed_metadata() -> None:
    # __version__ is read from the installed dist, so a single bump in
    # pyproject.toml is the single source of truth for the release number.
    assert roboflow_mcp.__version__ == metadata.version("mcp-server-roboflow")


def test_public_surface() -> None:
    # Tools arrive later; for now we only expose the version and server hooks.
    assert set(roboflow_mcp.__all__) == {"__version__", "build_server", "main"}
