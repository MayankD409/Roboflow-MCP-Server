"""Settings loaded from the environment.

The only required setting is ``ROBOFLOW_API_KEY``. Everything else has a sane
default so most users can just set the key and go.
"""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


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
