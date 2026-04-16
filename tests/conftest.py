"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import pytest
from pydantic import SecretStr

from roboflow_mcp.config import RoboflowSettings, ServerMode


class SettingsFactory(Protocol):
    """Callable that constructs a ``RoboflowSettings`` without env lookups."""

    def __call__(self, **overrides: Any) -> RoboflowSettings:
        """Build a fresh ``RoboflowSettings``."""


@pytest.fixture
def settings_factory() -> SettingsFactory:
    """Build a ``RoboflowSettings`` without touching the environment."""

    def _make(**overrides: Any) -> RoboflowSettings:
        defaults: dict[str, Any] = dict(
            api_key=SecretStr("k_test"),
            workspace=None,
            api_url="https://api.roboflow.com",
            log_level="INFO",
            # Default to ``CURATE`` mode so destructive impls can be exercised.
            # Tests that want readonly pass mode=readonly explicitly.
            mode=ServerMode.CURATE,
            allow_tools=frozenset(),
            deny_tools=frozenset(),
            workspace_allowlist=frozenset(),
            allow_insecure=False,
            audit_log_path=None,
            # Quotas raised so test suites don't trip them.
            rate_limit_per_minute=600,
            rate_limit_per_hour=10_000,
            circuit_breaker_threshold=100,
            circuit_breaker_cooldown_s=30.0,
            max_string_length=4096,
            max_list_length=1000,
            upload_roots=(),
            max_upload_bytes=25 * 1024 * 1024,
            export_cache_dir=Path("/tmp/roboflow-mcp-test-cache"),
            enable_downloads=True,
        )
        defaults.update(overrides)
        return RoboflowSettings.model_construct(**defaults)

    return _make
