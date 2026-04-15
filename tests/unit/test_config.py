"""Tests for roboflow_mcp.config."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from roboflow_mcp.config import RoboflowSettings


def test_loads_required_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "sk_test_abc123")
    monkeypatch.delenv("ROBOFLOW_WORKSPACE", raising=False)

    settings = RoboflowSettings()

    assert isinstance(settings.api_key, SecretStr)
    assert settings.api_key.get_secret_value() == "sk_test_abc123"


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROBOFLOW_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        RoboflowSettings(_env_file=None)


def test_api_key_never_leaks_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "super_secret_key_xyz")

    settings = RoboflowSettings()

    assert "super_secret_key_xyz" not in repr(settings)
    assert "super_secret_key_xyz" not in str(settings)


def test_defaults_for_optional_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.delenv("ROBOFLOW_WORKSPACE", raising=False)
    monkeypatch.delenv("ROBOFLOW_API_URL", raising=False)
    monkeypatch.delenv("ROBOFLOW_MCP_LOG_LEVEL", raising=False)

    # Ignore any on-disk .env so defaults are observable regardless of where
    # the test runs from.
    settings = RoboflowSettings(_env_file=None)

    assert settings.workspace is None
    assert settings.api_url == "https://api.roboflow.com"
    assert settings.log_level == "INFO"


def test_workspace_and_api_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv("ROBOFLOW_WORKSPACE", "contoro")
    monkeypatch.setenv("ROBOFLOW_API_URL", "https://proxy.example/api")

    settings = RoboflowSettings()

    assert settings.workspace == "contoro"
    assert settings.api_url == "https://proxy.example/api"


def test_log_level_is_normalised_to_upper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv("ROBOFLOW_MCP_LOG_LEVEL", "debug")

    settings = RoboflowSettings()

    assert settings.log_level == "DEBUG"


def test_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv("ROBOFLOW_MCP_LOG_LEVEL", "VERBOSE")

    with pytest.raises(ValidationError):
        RoboflowSettings()
