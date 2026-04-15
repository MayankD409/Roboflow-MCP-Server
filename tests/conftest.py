"""Shared pytest fixtures."""

from __future__ import annotations

from typing import Protocol

import pytest
from pydantic import SecretStr

from roboflow_mcp.config import RoboflowSettings


class SettingsFactory(Protocol):
    """Callable that constructs a ``RoboflowSettings`` without env lookups."""

    def __call__(
        self,
        api_key: str = ...,
        workspace: str | None = ...,
        api_url: str = ...,
        log_level: str = ...,
    ) -> RoboflowSettings: ...


@pytest.fixture
def settings_factory() -> SettingsFactory:
    """Build a ``RoboflowSettings`` without touching the environment."""

    def _make(
        api_key: str = "k_test",
        workspace: str | None = None,
        api_url: str = "https://api.roboflow.com",
        log_level: str = "INFO",
    ) -> RoboflowSettings:
        return RoboflowSettings.model_construct(
            api_key=SecretStr(api_key),
            workspace=workspace,
            api_url=api_url,
            log_level=log_level,
        )

    return _make
