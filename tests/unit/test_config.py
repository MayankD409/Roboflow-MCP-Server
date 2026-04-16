"""Tests for roboflow_mcp.config."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from roboflow_mcp.config import RoboflowSettings, ServerMode


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
    monkeypatch.delenv("ROBOFLOW_MCP_MODE", raising=False)

    # Ignore any on-disk .env so defaults are observable regardless of where
    # the test runs from.
    settings = RoboflowSettings(_env_file=None)

    assert settings.workspace is None
    assert settings.api_url == "https://api.roboflow.com"
    assert settings.log_level == "INFO"
    # Security defaults: readonly mode, strict TLS, no audit log path.
    assert settings.mode == ServerMode.READONLY
    assert settings.allow_insecure is False
    assert settings.audit_log_path is None
    assert settings.allow_tools == frozenset()
    assert settings.deny_tools == frozenset()
    assert settings.workspace_allowlist == frozenset()


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


def test_mode_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv("ROBOFLOW_MCP_MODE", "curate")

    settings = RoboflowSettings()
    assert settings.mode == ServerMode.CURATE


def test_mode_accepts_upper_and_mixed_case(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv("ROBOFLOW_MCP_MODE", "FULL")

    settings = RoboflowSettings()
    assert settings.mode == ServerMode.FULL


def test_invalid_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv("ROBOFLOW_MCP_MODE", "god_mode")

    with pytest.raises(ValidationError):
        RoboflowSettings()


def test_csv_lists_parse_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv(
        "ROBOFLOW_MCP_ALLOW_TOOLS",
        "roboflow_get_workspace, roboflow_list_projects",
    )
    monkeypatch.setenv("ROBOFLOW_MCP_DENY_TOOLS", "roboflow_remove_image_tags")
    monkeypatch.setenv("ROBOFLOW_MCP_WORKSPACE_ALLOWLIST", "contoro,acme")

    settings = RoboflowSettings()
    assert settings.allow_tools == frozenset(
        {"roboflow_get_workspace", "roboflow_list_projects"}
    )
    assert settings.deny_tools == frozenset({"roboflow_remove_image_tags"})
    assert settings.workspace_allowlist == frozenset({"contoro", "acme"})


def test_audit_log_path_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv("ROBOFLOW_MCP_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    settings = RoboflowSettings()
    assert settings.audit_log_path == tmp_path / "audit.jsonl"


def test_rate_limits_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv("ROBOFLOW_MCP_RATE_LIMIT_PER_MINUTE", "30")
    monkeypatch.setenv("ROBOFLOW_MCP_RATE_LIMIT_PER_HOUR", "500")

    settings = RoboflowSettings()
    assert settings.rate_limit_per_minute == 30
    assert settings.rate_limit_per_hour == 500


def test_allow_insecure_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
    monkeypatch.setenv("ROBOFLOW_MCP_ALLOW_INSECURE", "true")

    settings = RoboflowSettings()
    assert settings.allow_insecure is True
