"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pytest
from pydantic import SecretStr

from roboflow_mcp.config import RoboflowSettings, ServerMode


class SettingsFactory(Protocol):
    """Callable that constructs a ``RoboflowSettings`` without env lookups."""

    def __call__(
        self,
        api_key: str = ...,
        workspace: str | None = ...,
        api_url: str = ...,
        log_level: str = ...,
        mode: ServerMode = ...,
        allow_tools: frozenset[str] = ...,
        deny_tools: frozenset[str] = ...,
        workspace_allowlist: frozenset[str] = ...,
        allow_insecure: bool = ...,
        audit_log_path: Path | None = ...,
        rate_limit_per_minute: int = ...,
        rate_limit_per_hour: int = ...,
        circuit_breaker_threshold: int = ...,
        circuit_breaker_cooldown_s: float = ...,
        max_string_length: int = ...,
        max_list_length: int = ...,
    ) -> RoboflowSettings: ...


@pytest.fixture
def settings_factory() -> SettingsFactory:
    """Build a ``RoboflowSettings`` without touching the environment."""

    def _make(
        api_key: str = "k_test",
        workspace: str | None = None,
        api_url: str = "https://api.roboflow.com",
        log_level: str = "INFO",
        mode: ServerMode = ServerMode.CURATE,
        allow_tools: frozenset[str] = frozenset(),
        deny_tools: frozenset[str] = frozenset(),
        workspace_allowlist: frozenset[str] = frozenset(),
        allow_insecure: bool = False,
        audit_log_path: Path | None = None,
        rate_limit_per_minute: int = 600,
        rate_limit_per_hour: int = 10_000,
        circuit_breaker_threshold: int = 100,
        circuit_breaker_cooldown_s: float = 30.0,
        max_string_length: int = 4096,
        max_list_length: int = 1000,
    ) -> RoboflowSettings:
        # Default to ``CURATE`` mode in tests so destructive impls can be
        # exercised. Tests that want readonly behaviour pass mode=readonly
        # explicitly. Quotas are raised so test suites don't trip them.
        return RoboflowSettings.model_construct(
            api_key=SecretStr(api_key),
            workspace=workspace,
            api_url=api_url,
            log_level=log_level,
            mode=mode,
            allow_tools=allow_tools,
            deny_tools=deny_tools,
            workspace_allowlist=workspace_allowlist,
            allow_insecure=allow_insecure,
            audit_log_path=audit_log_path,
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_per_hour=rate_limit_per_hour,
            circuit_breaker_threshold=circuit_breaker_threshold,
            circuit_breaker_cooldown_s=circuit_breaker_cooldown_s,
            max_string_length=max_string_length,
            max_list_length=max_list_length,
        )

    return _make
