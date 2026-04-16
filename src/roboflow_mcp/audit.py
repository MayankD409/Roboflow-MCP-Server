"""JSONL audit log for every MCP tool invocation.

One line per call, written to the path in ``ROBOFLOW_MCP_AUDIT_LOG`` or to
stderr when that env var is unset. Schema:

    {
      "ts": <unix_seconds_float>,
      "tool": "<tool_name>",
      "mode": "<readonly|curate|full>",
      "workspace": "<slug or null>",
      "args_hash": "<sha256 hex prefix of redacted args>",
      "outcome": "<ok|error|denied|dry_run>",
      "http_status": <int or null>,
      "duration_ms": <float>,
      "error_class": "<exception class name or null>"
    }

Free-form user content is never written — only the hash of a
JSON-serialisable args dict. Callers are expected to scrub secrets from
``args`` before handing them in; the audit log deliberately does not try to
re-scrub.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO


class AuditLogger:
    """Append-only JSONL writer. Safe for single-process use."""

    def __init__(
        self, path: Path | None = None, *, stream: TextIO | None = None
    ) -> None:
        self._path = path
        self._stream = stream or (sys.stderr if path is None else None)
        if path is not None and self._stream is None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, default=str, separators=(",", ":"))
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        else:
            assert self._stream is not None
            self._stream.write(line + "\n")
            self._stream.flush()

    def log(
        self,
        *,
        tool: str,
        mode: str,
        workspace: str | None,
        args: dict[str, Any],
        outcome: str,
        http_status: int | None,
        duration_ms: float,
        error_class: str | None = None,
    ) -> None:
        record = {
            "ts": time.time(),
            "tool": tool,
            "mode": mode,
            "workspace": workspace,
            "args_hash": hash_args(args),
            "outcome": outcome,
            "http_status": http_status,
            "duration_ms": round(duration_ms, 3),
            "error_class": error_class,
        }
        self._write(record)

    @contextmanager
    def span(
        self,
        *,
        tool: str,
        mode: str,
        workspace: str | None,
        args: dict[str, Any],
    ) -> Iterator[_Span]:
        """Time-and-record a tool call. Always writes one audit line.

        Inside the block, callers set ``span.outcome`` and ``span.http_status``.
        On exception, ``outcome`` defaults to ``"error"`` and the exception
        class name is recorded under ``error_class``.
        """
        span = _Span(tool=tool, mode=mode, workspace=workspace, args=args)
        start = time.monotonic()
        try:
            yield span
        except Exception as exc:
            if span.outcome == _Span.DEFAULT_OUTCOME:
                span.outcome = "error"
            if span.error_class is None:
                span.error_class = type(exc).__name__
            self._finalize(span, start)
            raise
        self._finalize(span, start)

    def _finalize(self, span: _Span, start: float) -> None:
        duration_ms = (time.monotonic() - start) * 1000.0
        self.log(
            tool=span.tool,
            mode=span.mode,
            workspace=span.workspace,
            args=span.args,
            outcome=span.outcome,
            http_status=span.http_status,
            duration_ms=duration_ms,
            error_class=span.error_class,
        )


class _Span:
    """Mutable holder for outcome/http_status populated inside an audit span."""

    DEFAULT_OUTCOME = "ok"

    def __init__(
        self,
        *,
        tool: str,
        mode: str,
        workspace: str | None,
        args: dict[str, Any],
    ) -> None:
        self.tool = tool
        self.mode = mode
        self.workspace = workspace
        self.args = args
        self.outcome: str = self.DEFAULT_OUTCOME
        self.http_status: int | None = None
        self.error_class: str | None = None


def hash_args(args: dict[str, Any]) -> str:
    """Return the first 16 hex chars of the sha256 of a JSON-serialised args dict.

    ``sort_keys=True`` makes the hash stable across dict ordering. Non-JSON
    values fall back to ``str()``. The 16-char prefix is plenty to correlate
    related calls without turning the log into a reversible cookie.
    """
    blob = json.dumps(args, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
