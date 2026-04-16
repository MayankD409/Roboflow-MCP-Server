"""Tests for roboflow_mcp.audit."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from roboflow_mcp.audit import AuditLogger, hash_args


def test_hash_args_is_stable_under_key_reorder() -> None:
    assert hash_args({"a": 1, "b": 2}) == hash_args({"b": 2, "a": 1})


def test_hash_args_differs_for_different_values() -> None:
    assert hash_args({"x": 1}) != hash_args({"x": 2})


def test_hash_args_returns_16_hex_chars() -> None:
    h = hash_args({"tool": "x"})
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_args_handles_non_json_values() -> None:
    # pathlib.Path isn't natively JSON-serialisable but hash_args uses
    # default=str so it shouldn't raise.
    hash_args({"p": Path("/tmp/x")})


def test_log_writes_single_jsonl_line_to_stream() -> None:
    buf = io.StringIO()
    logger = AuditLogger(path=None, stream=buf)
    logger.log(
        tool="roboflow_get_workspace",
        mode="readonly",
        workspace="contoro",
        args={"workspace": "contoro"},
        outcome="ok",
        http_status=200,
        duration_ms=12.3,
    )
    text = buf.getvalue().strip()
    assert text.count("\n") == 0  # single line
    payload = json.loads(text)
    assert payload["tool"] == "roboflow_get_workspace"
    assert payload["mode"] == "readonly"
    assert payload["workspace"] == "contoro"
    assert payload["outcome"] == "ok"
    assert payload["http_status"] == 200
    assert payload["duration_ms"] == 12.3
    assert "args_hash" in payload
    assert payload["error_class"] is None


def test_log_never_contains_raw_args(tmp_path: Path) -> None:
    """The audit log must never store the raw arguments dict."""
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path=path)
    logger.log(
        tool="roboflow_add_image_tags",
        mode="curate",
        workspace="contoro",
        args={"api_key": "leaked_secret_XYZ", "tags": ["leaked_tag"]},
        outcome="ok",
        http_status=200,
        duration_ms=5.0,
    )
    text = path.read_text(encoding="utf-8")
    assert "leaked_secret_XYZ" not in text
    assert "leaked_tag" not in text
    # But the hash is present and deterministic.
    payload = json.loads(text.strip())
    assert payload["args_hash"] == hash_args(
        {"api_key": "leaked_secret_XYZ", "tags": ["leaked_tag"]}
    )


def test_span_records_outcome_on_success() -> None:
    buf = io.StringIO()
    logger = AuditLogger(path=None, stream=buf)
    with logger.span(tool="t", mode="curate", workspace=None, args={"k": "v"}) as span:
        span.outcome = "dry_run"
        span.http_status = None
    record = json.loads(buf.getvalue().strip())
    assert record["outcome"] == "dry_run"
    assert record["error_class"] is None
    assert record["duration_ms"] >= 0.0


def test_span_records_error_class_on_exception() -> None:
    buf = io.StringIO()
    logger = AuditLogger(path=None, stream=buf)
    with (
        pytest.raises(ValueError),
        logger.span(tool="t", mode="curate", workspace=None, args={"k": "v"}),
    ):
        raise ValueError("boom")
    record = json.loads(buf.getvalue().strip())
    assert record["outcome"] == "error"
    assert record["error_class"] == "ValueError"


def test_file_path_is_created_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "sub" / "audit.jsonl"
    logger = AuditLogger(path=nested)
    logger.log(
        tool="t",
        mode="readonly",
        workspace=None,
        args={},
        outcome="ok",
        http_status=None,
        duration_ms=0.0,
    )
    assert nested.exists()
