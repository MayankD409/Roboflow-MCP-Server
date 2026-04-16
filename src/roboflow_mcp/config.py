"""Settings loaded from the environment.

The only required setting is ``ROBOFLOW_API_KEY``. Everything else has a sane
default. Security-relevant knobs default to the most restrictive option
(read-only mode, strict TLS, modest quotas) so an operator must opt in to
anything risky.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


class ServerMode(str, Enum):
    """Capability scope applied to every tool call.

    ``readonly`` blocks destructive operations (tag removals, future deletes).
    ``curate`` allows dataset curation (tag removals, uploads, deletes, etc.).
    ``full`` additionally allows quota-heavy or training/inference ops.
    """

    READONLY = "readonly"
    CURATE = "curate"
    FULL = "full"

    @classmethod
    def allows_destructive(cls, mode: ServerMode) -> bool:
        return mode in (cls.CURATE, cls.FULL)


def _parse_csv(raw: object) -> frozenset[str]:
    """Parse a comma-separated env var into a frozen set of trimmed tokens."""
    if raw is None or raw == "":
        return frozenset()
    if isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset(str(v).strip() for v in raw if str(v).strip())
    text = str(raw)
    return frozenset(part.strip() for part in text.split(",") if part.strip())


def _parse_path_list(raw: object) -> tuple[Path, ...]:
    """Parse a comma-separated env var into a tuple of ``Path``.

    Leaves the ``Path`` objects unresolved — callers that need the
    canonical filesystem path (e.g. the path guard) resolve at use time
    so we don't stat the filesystem at settings load.
    """
    if raw is None or raw == "":
        return ()
    if isinstance(raw, (list, tuple, set, frozenset)):
        items = [str(v).strip() for v in raw if str(v).strip()]
    else:
        items = [part.strip() for part in str(raw).split(",") if part.strip()]
    return tuple(Path(item).expanduser() for item in items)


class RoboflowSettings(BaseSettings):
    """Runtime settings for the Roboflow MCP server.

    Set these as environment variables or put them in a ``.env`` file alongside
    the project. The API key is stored as a :class:`~pydantic.SecretStr` so it
    never sneaks into a ``repr`` or a log line.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_key: SecretStr = Field(..., alias="ROBOFLOW_API_KEY")
    workspace: str | None = Field(default=None, alias="ROBOFLOW_WORKSPACE")
    api_url: str = Field(
        default="https://api.roboflow.com",
        alias="ROBOFLOW_API_URL",
    )
    log_level: str = Field(default="INFO", alias="ROBOFLOW_MCP_LOG_LEVEL")

    # --- capability model ------------------------------------------------
    # The allow/deny lists take a CSV string from the env (e.g.
    # "roboflow_get_workspace, roboflow_list_projects"). NoDecode stops
    # pydantic-settings from trying to JSON-parse the value first, so the
    # CSV reaches our field_validator untouched.
    mode: ServerMode = Field(default=ServerMode.READONLY, alias="ROBOFLOW_MCP_MODE")
    allow_tools: Annotated[frozenset[str], NoDecode] = Field(
        default_factory=frozenset,
        alias="ROBOFLOW_MCP_ALLOW_TOOLS",
    )
    deny_tools: Annotated[frozenset[str], NoDecode] = Field(
        default_factory=frozenset,
        alias="ROBOFLOW_MCP_DENY_TOOLS",
    )
    workspace_allowlist: Annotated[frozenset[str], NoDecode] = Field(
        default_factory=frozenset,
        alias="ROBOFLOW_MCP_WORKSPACE_ALLOWLIST",
    )

    # --- transport / TLS -------------------------------------------------
    allow_insecure: bool = Field(default=False, alias="ROBOFLOW_MCP_ALLOW_INSECURE")

    # --- observability ---------------------------------------------------
    audit_log_path: Path | None = Field(default=None, alias="ROBOFLOW_MCP_AUDIT_LOG")

    # --- quotas / circuit breaker ----------------------------------------
    rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        alias="ROBOFLOW_MCP_RATE_LIMIT_PER_MINUTE",
    )
    rate_limit_per_hour: int = Field(
        default=1000,
        ge=1,
        alias="ROBOFLOW_MCP_RATE_LIMIT_PER_HOUR",
    )
    circuit_breaker_threshold: int = Field(
        default=5,
        ge=1,
        alias="ROBOFLOW_MCP_CIRCUIT_BREAKER_THRESHOLD",
    )
    circuit_breaker_cooldown_s: float = Field(
        default=30.0,
        gt=0,
        alias="ROBOFLOW_MCP_CIRCUIT_BREAKER_COOLDOWN",
    )

    # --- input bounds ----------------------------------------------------
    max_string_length: int = Field(
        default=4096,
        ge=1,
        alias="ROBOFLOW_MCP_MAX_STRING_LENGTH",
    )
    max_list_length: int = Field(
        default=1000,
        ge=1,
        alias="ROBOFLOW_MCP_MAX_LIST_LENGTH",
    )

    # --- ingestion (v0.3) ------------------------------------------------
    # `upload_roots` is the allowlist of directories under which local-file
    # uploads may originate. Unset = path uploads disabled; caller must
    # use url / base64 sources instead.
    upload_roots: Annotated[tuple[Path, ...], NoDecode] = Field(
        default=(),
        alias="ROBOFLOW_MCP_UPLOAD_ROOTS",
    )
    max_upload_bytes: int = Field(
        default=25 * 1024 * 1024,
        ge=1,
        alias="ROBOFLOW_MCP_MAX_UPLOAD_BYTES",
    )
    export_cache_dir: Path = Field(
        default=Path.home() / ".cache" / "roboflow-mcp",
        alias="ROBOFLOW_MCP_EXPORT_CACHE_DIR",
    )
    enable_downloads: bool = Field(
        default=True,
        alias="ROBOFLOW_MCP_ENABLE_DOWNLOADS",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        normalised = value.upper() if isinstance(value, str) else value
        if normalised not in _ALLOWED_LOG_LEVELS:
            raise ValueError(
                f"Invalid log level {value!r}; expected one of "
                f"{sorted(_ALLOWED_LOG_LEVELS)}"
            )
        return normalised

    @field_validator("mode", mode="before")
    @classmethod
    def _normalise_mode(cls, value: object) -> object:
        if isinstance(value, ServerMode):
            return value
        if isinstance(value, str):
            return value.lower()
        return value

    @field_validator("allow_tools", "deny_tools", "workspace_allowlist", mode="before")
    @classmethod
    def _parse_allowlists(cls, value: object) -> frozenset[str]:
        return _parse_csv(value)

    @field_validator("upload_roots", mode="before")
    @classmethod
    def _parse_upload_roots(cls, value: object) -> tuple[Path, ...]:
        return _parse_path_list(value)
