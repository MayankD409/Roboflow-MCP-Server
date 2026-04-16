"""Wrap Roboflow-origin strings as data, not instructions.

Prompt-injection defense in depth. Any string field that comes back from the
Roboflow API (image names, tag names, project descriptions, workflow block
outputs) might contain instructions crafted to steer the LLM. We envelope
those strings inside a JSON object with a distinctive key so well-behaved
clients render them as data and poorly-behaved clients still get a hint that
the content is untrusted.

The envelope shape is intentionally boring: ``{"untrusted": "...", "truncated": bool}``.
"""

from __future__ import annotations

from typing import Any

_MAX_UNTRUSTED_BYTES = 8 * 1024  # 8 KiB — generous for a single user-visible field


def sanitize_untrusted(
    value: object, *, max_bytes: int = _MAX_UNTRUSTED_BYTES
) -> dict[str, Any]:
    """Envelope an untrusted value as a data payload.

    The value is coerced to ``str``, UTF-8 encoded, and truncated to
    ``max_bytes``. The result is JSON-serialisable and safe to embed in any
    MCP response without instructing the LLM.
    """
    text = value if isinstance(value, str) else str(value)
    encoded = text.encode("utf-8")
    truncated = len(encoded) > max_bytes
    if truncated:
        # Truncate on a codepoint boundary so downstream json.dumps doesn't choke
        encoded = encoded[:max_bytes]
        text = encoded.decode("utf-8", errors="ignore")
    return {"untrusted": text, "truncated": truncated}


def wrap_untrusted_dict(
    payload: dict[str, Any],
    *,
    string_keys: tuple[str, ...],
    max_bytes: int = _MAX_UNTRUSTED_BYTES,
) -> dict[str, Any]:
    """Return a shallow copy of ``payload`` with the named keys enveloped.

    Only the listed string keys are touched; lists, dicts, numbers, and
    anything else are passed through unchanged. Use this when you have a
    known-schema response (e.g. a project summary) and want to wrap the
    user-controlled fields.
    """
    wrapped: dict[str, Any] = {}
    for key, value in payload.items():
        if key in string_keys and isinstance(value, str):
            wrapped[key] = sanitize_untrusted(value, max_bytes=max_bytes)
        else:
            wrapped[key] = value
    return wrapped
