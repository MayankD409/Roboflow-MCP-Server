"""Logging setup with a secret-scrubbing formatter.

We run through the whole MCP server with a single formatter that replaces the
Roboflow API key -- either as a literal string or inside ``api_key=`` query
params -- with ``***``. This keeps accidental leaks out of stdout and any log
files users pipe us into.
"""

from __future__ import annotations

import logging
import re

_API_KEY_QUERY_PATTERN = re.compile(
    r"(api_key=)[^&\s\"'<>]+",
    flags=re.IGNORECASE,
)


def scrub_secret(text: str, secret: str) -> str:
    """Replace ``secret`` and ``api_key=<value>`` patterns with ``***``."""
    if secret:
        text = text.replace(secret, "***")
    return _API_KEY_QUERY_PATTERN.sub(r"\1***", text)


class SecretScrubbingFormatter(logging.Formatter):
    """Formatter that scrubs a known secret from every formatted record."""

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        *,
        secret: str = "",
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._secret = secret

    def format(self, record: logging.LogRecord) -> str:
        return scrub_secret(super().format(record), self._secret)


def configure_logging(level: str, *, secret: str) -> None:
    """Install a single stream handler on the root logger.

    Idempotent: replaces any existing handlers so we don't double-print.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        SecretScrubbingFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            secret=secret,
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
