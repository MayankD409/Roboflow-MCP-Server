"""Tests for roboflow_mcp.safety.paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from roboflow_mcp.errors import PathGuardError
from roboflow_mcp.safety.paths import resolve_local_path


def _make_file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_happy_path(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    target = _make_file(root / "img.jpg")
    resolved = resolve_local_path(target, [root])
    assert resolved == target.resolve(strict=True)


def test_nested_directory_ok(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    target = _make_file(root / "sub" / "img.jpg")
    assert resolve_local_path(target, [root]) == target.resolve(strict=True)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PathGuardError, match="does not exist"):
        resolve_local_path(tmp_path / "nope.jpg", [tmp_path])


def test_directory_not_allowed(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    with pytest.raises(PathGuardError, match="not a regular file"):
        resolve_local_path(tmp_path / "subdir", [tmp_path])


def test_outside_root_rejected(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    target = _make_file(tmp_path / "outside.jpg")
    with pytest.raises(PathGuardError, match="not under"):
        resolve_local_path(target, [root])


def test_parent_traversal_rejected(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    outside = _make_file(tmp_path / "secret.txt")
    sneaky = root / ".." / "secret.txt"
    with pytest.raises(PathGuardError, match="not under"):
        resolve_local_path(sneaky, [root])
    # Sanity: we didn't accidentally let it through
    assert outside.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_symlink_rejected(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    real = _make_file(tmp_path / "real.jpg")
    link = root / "link.jpg"
    os.symlink(real, link)
    with pytest.raises(PathGuardError, match="symlink"):
        resolve_local_path(link, [root])


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_symlink_in_parent_rejected(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    _make_file(real_dir / "x.jpg")
    # Put a symlinked subdirectory inside the root
    linked = root / "linked_subdir"
    os.symlink(real_dir, linked)
    with pytest.raises(PathGuardError, match="symlink"):
        resolve_local_path(linked / "x.jpg", [root])


def test_empty_allowed_roots_rejects(tmp_path: Path) -> None:
    target = _make_file(tmp_path / "x.jpg")
    with pytest.raises(PathGuardError, match="No upload roots"):
        resolve_local_path(target, [])


def test_missing_allowed_root_raises(tmp_path: Path) -> None:
    target = _make_file(tmp_path / "x.jpg")
    missing_root = tmp_path / "nowhere"
    with pytest.raises(PathGuardError, match="does not exist"):
        resolve_local_path(target, [missing_root])


def test_multiple_roots_matches_first(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    target = _make_file(root_b / "x.jpg")
    resolved = resolve_local_path(target, [root_a, root_b])
    assert resolved == target.resolve(strict=True)
