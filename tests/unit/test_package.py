"""Smoke tests for the package itself. Prove the scaffold is import-clean."""

from __future__ import annotations

import roboflow_mcp


def test_version_is_a_string() -> None:
    assert isinstance(roboflow_mcp.__version__, str)
    assert roboflow_mcp.__version__


def test_public_surface() -> None:
    # Tools arrive later; for now we only expose the version and server hooks.
    assert set(roboflow_mcp.__all__) == {"__version__", "build_server", "main"}
