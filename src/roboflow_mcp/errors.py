"""Typed exceptions for the Roboflow MCP server.

Every error the server raises inherits from :class:`RoboflowMCPError`, which
makes it easy for the MCP layer to map them onto JSON-RPC error payloads
without catching unrelated exceptions by accident.
"""

from __future__ import annotations


class RoboflowMCPError(Exception):
    """Base class for all errors raised by this package."""


class ConfigurationError(RoboflowMCPError):
    """Raised when configuration is missing or invalid."""


class AuthenticationError(RoboflowMCPError):
    """Raised when Roboflow rejects the API key."""


class NotFoundError(RoboflowMCPError):
    """Raised when a Roboflow resource does not exist."""


class RateLimitError(RoboflowMCPError):
    """Raised when Roboflow returns 429. Carries the retry-after hint if any."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class RoboflowAPIError(RoboflowMCPError):
    """Generic Roboflow API failure. Keeps status and payload for logging."""

    def __init__(
        self,
        status: int,
        message: str,
        *,
        payload: dict[str, object] | None = None,
    ) -> None:
        super().__init__(f"Roboflow API {status}: {message}")
        self.status = status
        self.payload: dict[str, object] = payload or {}


class ToolDisabledError(ConfigurationError):
    """Raised when a tool is denied by allow/deny lists or server mode."""


class QuotaExceededError(RoboflowMCPError):
    """Raised when the client-side rate limit is exceeded."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class CircuitOpenError(RoboflowMCPError):
    """Raised when the circuit breaker has tripped and is cooling down."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class SafetyError(RoboflowMCPError):
    """Raised when a safety guard (URL / path / image) rejects an input."""


class UrlGuardError(SafetyError):
    """Raised when a URL fails the SSRF / scheme / size guard."""


class PathGuardError(SafetyError):
    """Raised when a local path escapes the configured upload roots."""


class ImageGuardError(SafetyError):
    """Raised when image content fails validation (format, size, dimensions)."""
