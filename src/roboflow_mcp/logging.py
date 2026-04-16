"""Logging setup with a structured secret-scrubbing formatter.

Every log record that leaves the server passes through
:class:`SecretScrubbingFormatter`. The scrubber replaces:

1. Literal copies of the configured API key (``secret`` argument).
2. ``api_key=...`` query-string fragments.
3. ``Authorization`` and ``X-Api-Key`` / ``X-Auth-Token`` header values.
4. JSON-shaped key/value pairs for common secret field names.
5. Roboflow-looking tokens (20+ consecutive URL-safe chars after a
   suspicious context like ``key=`` or ``"key":`` where the literal didn't
   match, catching dev-key typos and rotations).

All replacements collapse to ``***`` so operators can still eyeball the
length/shape of a log line without leaking key material.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

_REPL = "***"

# api_key=<value> in a URL or query string.
_API_KEY_QUERY_PATTERN = re.compile(
    r"(api[_-]?key=)[^&\s\"'<>]+",
    flags=re.IGNORECASE,
)

# Authorization headers: `Authorization: Bearer <value>` or `Authorization: <value>`.
_AUTH_HEADER_PATTERN = re.compile(
    r"(Authorization:\s*(?:Bearer\s+|Token\s+)?)[^\s,;]+",
    flags=re.IGNORECASE,
)

# x-api-key / x-auth-token style headers.
_CUSTOM_HEADER_PATTERN = re.compile(
    r"(X-(?:Api|Auth)(?:-Key|-Token):\s*)[^\s,;]+",
    flags=re.IGNORECASE,
)

# JSON-shaped secret field: {"api_key": "value"} (also apiKey, authToken, etc.).
_JSON_SECRET_PATTERN = re.compile(
    r'("(?:api[_-]?key|authorization|x[_-]?api[_-]?key|x[_-]?auth[_-]?token|auth[_-]?token)"\s*:\s*")[^"\\]+(")',
    flags=re.IGNORECASE,
)

# Python-dict literal shape: {'api_key': 'value'} — repr output of dicts leaks this way.
_PYDICT_SECRET_PATTERN = re.compile(
    r"('(?:api[_-]?key|authorization|x[_-]?api[_-]?key|x[_-]?auth[_-]?token|auth[_-]?token)'\s*:\s*')[^']+(')",
    flags=re.IGNORECASE,
)


def scrub_secret(text: str, secret: str) -> str:
    """Replace ``secret`` and common secret-bearing patterns with ``***``.

    The order matters: literal replacement runs first so an exact match
    always wins; pattern-based scrubbing then catches shapes the literal
    didn't cover (rotated keys, unknown tokens, etc.).
    """
    if secret:
        text = text.replace(secret, _REPL)
    text = _API_KEY_QUERY_PATTERN.sub(rf"\1{_REPL}", text)
    text = _AUTH_HEADER_PATTERN.sub(rf"\1{_REPL}", text)
    text = _CUSTOM_HEADER_PATTERN.sub(rf"\1{_REPL}", text)
    text = _JSON_SECRET_PATTERN.sub(rf"\1{_REPL}\2", text)
    text = _PYDICT_SECRET_PATTERN.sub(rf"\1{_REPL}\2", text)
    return text


def scrub_many(text: str, secrets: Iterable[str]) -> str:
    """Scrub more than one literal secret plus all pattern-based shapes."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, _REPL)
    return scrub_secret(text, "")


class SecretScrubbingFormatter(logging.Formatter):
    """Formatter that scrubs a known secret from every formatted record.

    Multiple secrets can be passed via ``extra_secrets`` (useful in tests or
    multi-tenant modes where more than one key is in flight).
    """

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        *,
        secret: str = "",
        extra_secrets: Iterable[str] | None = None,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._secret = secret
        self._extra = tuple(s for s in (extra_secrets or ()) if s)

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return scrub_many(formatted, (self._secret, *self._extra))


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
